from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from ask_esafe_ai.ask_esafe_ai import purchase_order_scan as scan


class UnitTestPurchaseOrderScan(UnitTestCase):
	def documents(self, filename="quotation.pdf", attached_to="conversation"):
		conversation = SimpleNamespace(
			doctype="ASK ESAFE AI Conversation", name="conversation", check_permission=Mock(),
		)
		file = SimpleNamespace(
			name="source-file", file_name=filename, check_permission=Mock(),
			attached_to_doctype=conversation.doctype, attached_to_name=attached_to,
		)
		return conversation, file

	def test_preparing_scan_checks_permissions_and_uses_the_installed_skill(self):
		conversation, file = self.documents()
		with (
			patch.object(scan, "_scan_context", return_value={"ready": True}),
			patch("ask_esafe_ai.ask_esafe_ai.skill_utils.get_accessible_skill_doc") as check_skill,
			patch.object(frappe, "get_doc", side_effect=[conversation, file]),
		):
			result = scan.prepare_scan(file.name, conversation.name)
		check_skill.assert_called_once_with(scan.SKILL_NAME)
		conversation.check_permission.assert_called_once_with("write")
		file.check_permission.assert_called_once_with("read")
		self.assertIn(scan.SKILL_NAME, result["message"])
		self.assertIn(file.name, result["message"])
		self.assertIn("confirmation", result["message"])

	def test_scan_rejects_a_file_from_another_conversation(self):
		conversation, file = self.documents(attached_to="other-conversation")
		with (
			patch.object(scan, "_scan_context", return_value={"ready": True}),
			patch("ask_esafe_ai.ask_esafe_ai.skill_utils.get_accessible_skill_doc"),
			patch.object(frappe, "get_doc", side_effect=[conversation, file]),
		):
			with self.assertRaises(frappe.PermissionError):
				scan.prepare_scan(file.name, conversation.name)

	def test_scan_rejects_unsupported_files(self):
		conversation, file = self.documents(filename="script.html")
		with (
			patch.object(scan, "_scan_context", return_value={"ready": True}),
			patch("ask_esafe_ai.ask_esafe_ai.skill_utils.get_accessible_skill_doc"),
			patch.object(frappe, "get_doc", side_effect=[conversation, file]),
		):
			with self.assertRaises(frappe.ValidationError):
				scan.prepare_scan(file.name, conversation.name)

	def test_scan_rejects_disabled_or_unauthorized_workflow(self):
		with patch.object(scan, "_scan_context", return_value={"ready": False, "reason": "Access required"}):
			with self.assertRaises(frappe.PermissionError):
				scan.prepare_scan("source-file", "conversation")

	def test_installation_preserves_an_existing_customized_skill(self):
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_doc") as get_doc,
		):
			scan.install_skill()
		get_doc.assert_not_called()
