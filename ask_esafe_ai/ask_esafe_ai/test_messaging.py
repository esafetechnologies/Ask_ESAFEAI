from contextlib import contextmanager
from datetime import datetime, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from werkzeug.wrappers import Request

from ask_esafe_ai.ask_esafe_ai import messaging as chat
from ask_esafe_ai.ask_esafe_ai import whatsapp


@contextmanager
def as_user(user):
	original = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(original)


class IntegrationTestMessaging(IntegrationTestCase):
	def make_user(self):
		user = frappe.get_doc({
			"doctype": "User", "email": f"test-chat-{frappe.generate_hash(length=10)}@example.com",
			"first_name": "Chat Test", "enabled": 1, "user_type": "System User", "send_welcome_email": 0,
			"roles": [{"role": chat.TEAM_ROLE}],
		})
		return user.insert(ignore_permissions=True).name

	def test_direct_conversation_and_send_retry_are_idempotent(self):
		first, second = self.make_user(), self.make_user()
		with as_user(first), patch.object(chat, "changed"), patch.object(
			frappe.local, "request", Request.from_values(method="POST"), create=True,
		):
			thread = chat.start_thread([second])
			key = "enough-entropy-for-a-client-key"
			message = chat.send(thread, key, "Hello")
			self.assertEqual(chat.send(thread, key, "Hello"), message)
		with as_user(second), patch.object(chat, "changed"):
			self.assertEqual(chat.start_thread([first]), thread)
			self.assertEqual([item["body"] for item in chat.history(thread)["messages"]], ["Hello"])
		self.assertEqual(frappe.db.count(chat.MESSAGE, {"thread": thread}), 1)

	def test_removal_and_rejoin_enforce_history_and_download_access(self):
		owner, initial, newcomer = (self.make_user() for _ in range(3))
		upload = Request.from_values(method="POST", data={"file": (BytesIO(b"private data"), "private.txt")})
		download = Request.from_values(method="GET")
		with patch.object(chat, "changed"):
			with as_user(owner), patch.object(frappe.local, "request", upload, create=True):
				thread = chat.start_thread([initial], "Private group", group=1)
				old_file = chat.send(thread, "client-key-first-upload")
				chat.update_group(thread, "add", newcomer)
			with as_user(newcomer), patch.object(frappe.local, "request", download, create=True):
				self.assertEqual(chat.history(thread)["messages"], [])
				with self.assertRaises(frappe.PermissionError):
					chat.download(old_file)
			second_upload = Request.from_values(method="POST", data={"file": (BytesIO(b"new data"), "new.txt")})
			with as_user(newcomer), patch.object(frappe.local, "request", second_upload, create=True):
				new_file = chat.send(thread, "client-key-second-upload")
				file = frappe.get_doc("File", frappe.db.get_value(chat.MESSAGE, new_file, "file_id"))
				self.assertEqual(file.owner, "Administrator")
				self.assertNotEqual(file.get_content(), b"new data")
			with as_user(newcomer), patch.object(frappe.local, "request", download, create=True):
				response = chat.download(new_file)
				response.direct_passthrough = False
				self.assertEqual(response.get_data(), b"new data")
			with as_user(owner):
				chat.update_group(thread, "remove", newcomer)
			with as_user(newcomer), patch.object(frappe.local, "request", download, create=True):
				with self.assertRaises(frappe.PermissionError):
					chat.download(new_file)
			with as_user(owner):
				chat.update_group(thread, "add", newcomer)
			with as_user(newcomer), patch.object(frappe.local, "request", download, create=True):
				self.assertEqual(chat.history(thread)["messages"], [])
				with self.assertRaises(frappe.PermissionError):
					chat.download(new_file)


class UnitTestWhatsAppMessaging(UnitTestCase):
	def test_directory_includes_users_with_effective_messaging_access(self):
		administrator = frappe._dict(name="Administrator", full_name="Administrator")
		staff = frappe._dict(name="staff@example.com", full_name="Staff")
		other = frappe._dict(name="other@example.com", full_name="Other")
		with (
			patch.object(frappe, "get_all", return_value=[administrator, staff, other]) as get_all,
			patch.object(chat, "has_role", side_effect=lambda role, user: user in {"Administrator", staff.name}),
		):
			self.assertEqual(chat.eligible_users(chat.TEAM_ROLE), [administrator, staff])
			get_all.assert_called_once_with("User", filters={"enabled": 1, "user_type": "System User"},
				fields=["name", "full_name"], order_by="full_name asc")

	def test_group_access_requires_active_membership(self):
		thread = SimpleNamespace(name="private-thread", kind="Group")
		with patch.object(chat, "membership", return_value=None), patch.object(chat, "has_role", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				chat.check_thread(thread)

	def test_history_always_filters_on_join_boundary(self):
		member = SimpleNamespace(joined_after=17, last_read=17)
		with (
			patch.object(chat, "get_thread", return_value=SimpleNamespace(name="thread")),
			patch.object(chat, "check_thread", return_value=member),
			patch.object(frappe, "get_all", return_value=[]) as get_all,
		):
			chat.history("thread", before=12)
			self.assertIn(["sequence", ">", 17], get_all.call_args.kwargs["filters"])
			self.assertIn(["sequence", "<", 12], get_all.call_args.kwargs["filters"])

	def test_restricted_record_attachment_hides_metadata(self):
		row = frappe._dict(name="message", record_file="restricted-file", file_id=None, media_id=None)
		with patch.object(chat, "safe_record_file", return_value=None):
			result = chat.public_message(row, "test@example.com")
			self.assertIsNone(result["attachment"])
			self.assertTrue(result["restricted"])

	def test_download_before_join_boundary_is_denied(self):
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_doc", return_value=SimpleNamespace(thread="thread", sequence=5)),
			patch.object(chat, "get_thread"),
			patch.object(chat, "check_thread", return_value=SimpleNamespace(joined_after=5)),
		):
			with self.assertRaises(frappe.PermissionError):
				chat.download("message")

	def test_claim_rejects_agent_when_conversation_is_already_assigned(self):
		thread = SimpleNamespace(name="wa-thread", kind="WhatsApp", assignee="another@example.com")
		with (
			patch.object(chat, "require_role", return_value="me@example.com"),
			patch.object(chat, "get_thread", return_value=thread),
			patch.object(chat, "check_thread"),
		):
			with self.assertRaises(frappe.PermissionError):
				whatsapp.assign("wa-thread")

	def test_templates_require_recorded_customer_consent(self):
		thread = SimpleNamespace(opted_in=False)
		settings = SimpleNamespace(approved_templates="follow_up:en_US")
		with patch.object(whatsapp, "configuration", return_value=(settings, {})):
			with self.assertRaises(frappe.ValidationError):
				whatsapp.validate_outbound(thread, "follow_up:en_US", False, False)

	def test_provider_replay_does_not_append_a_duplicate_message(self):
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value="existing-message"),
			patch.object(chat, "get_thread", return_value=SimpleNamespace(name="wa-thread")),
			patch.object(chat, "append_message") as append,
		):
			whatsapp.incoming("business-id", {"from": "94771234567", "id": "provider-message"}, "Customer")
			append.assert_not_called()

	def test_notification_query_is_scoped_to_recipient(self):
		with patch.object(frappe, "get_all", return_value=[]) as get_all:
			self.assertEqual(chat.notifications("recipient@example.com"), [])
			self.assertEqual(get_all.call_args.kwargs["filters"], {"for_user": "recipient@example.com"})

	def test_free_form_reply_window_closes_at_exactly_24_hours(self):
		now = datetime(2026, 11, 17, 12)
		with patch.object(whatsapp, "utc_now", return_value=now):
			thread = SimpleNamespace(last_inbound=now - timedelta(hours=24))
			self.assertFalse(whatsapp.reply_open(thread))
			thread.last_inbound += timedelta(seconds=1)
			self.assertTrue(whatsapp.reply_open(thread))

	def test_invalid_signature_is_rejected_before_processing(self):
		request = Request.from_values(method="POST", json={"object": "whatsapp_business_account"},
			headers={"X-Hub-Signature-256": "sha256=incorrect"})
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(whatsapp, "configuration", return_value=(None, {"app_secret": "app-secret"})),
			patch.object(whatsapp, "incoming") as incoming,
		):
			self.assertEqual(whatsapp.webhook().status_code, 403)
			incoming.assert_not_called()
