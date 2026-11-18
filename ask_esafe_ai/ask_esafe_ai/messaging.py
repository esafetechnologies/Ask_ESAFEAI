from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import UTC, timedelta
from io import BytesIO
from pathlib import PurePath

import frappe
from cryptography.fernet import Fernet
from frappe import _
from frappe.sessions import get_csrf_token
from frappe.utils import cint, get_datetime, now_datetime, strip_html
from frappe.utils.password import get_encryption_key
from werkzeug.utils import send_file

THREAD = "ASK ESAFE AI Chat Thread"
MEMBER = "ASK ESAFE AI Chat Member"
MESSAGE = "ASK ESAFE AI Chat Message"
SETTINGS = "ASK ESAFE AI WhatsApp Settings"
TEAM_ROLE = "ASK ESAFE AI Messaging User"
AGENT_ROLE = "ASK ESAFE AI WhatsApp Agent"
EVENT = "ask_esafe_ai_messaging_changed"
FILE_LIMIT = 16 * 1024 * 1024
MESSAGE_FIELDS = [
	"name", "thread", "sequence", "sender", "direction", "body", "file_id", "file_label",
	"record_file", "status", "media_id", "creation", "modified",
]


def has_role(role, user=None):
	user = user or frappe.session.user
	return (
		user != "Guest"
		and frappe.get_cached_value("User", user, "enabled")
		and frappe.get_cached_value("User", user, "user_type") == "System User"
		and role in frappe.get_roles(user)
	)


def require_role(role):
	if not has_role(role):
		deny()
	return frappe.session.user


def deny():
	frappe.throw(_("You do not have access to this conversation or item."), frappe.PermissionError)


def identifier(*parts):
	return hashlib.sha256(frappe.as_json(parts).encode()).hexdigest()


def get_thread(name, lock=False):
	if not name:
		deny()
	try:
		return frappe.get_doc(THREAD, name, for_update=lock)
	except frappe.DoesNotExistError:
		deny()


def membership(thread, user, lock=False):
	return frappe.db.get_value(
		MEMBER, {"thread": thread, "user": user, "active": 1}, ["name", "joined_after", "last_read"],
		as_dict=True, for_update=lock,
	)


def check_thread(thread, user=None, lock=False):
	user = user or frappe.session.user
	member = membership(thread.name, user, lock)
	if thread.kind == "WhatsApp":
		if (
			not has_role(AGENT_ROLE, user) or not frappe.db.get_single_value(SETTINGS, "enabled")
			or thread.business_phone_id != frappe.db.get_single_value(SETTINGS, "phone_number_id")
		):
			deny()
	elif not has_role(TEAM_ROLE, user) or not member:
		deny()
	return member


def insert(doctype, name=None, **fields):
	return frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True, set_name=name)


def set_member(thread, user, sequence=0):
	row = identifier("member", thread, user)
	fields = {"active": 1, "joined_after": sequence, "last_read": sequence}
	if frappe.db.exists(MEMBER, row):
		frappe.db.set_value(MEMBER, row, fields)
	else:
		insert(MEMBER, row, thread=thread, user=user, **fields)


def eligible_users(role):
	users = frappe.get_all(
		"User", filters={"enabled": 1, "user_type": "System User"},
		fields=["name", "full_name"], order_by="full_name asc",
	)
	return [user for user in users if has_role(role, user.name)]


def changed(thread, extra=()):
	if thread.kind == "WhatsApp":
		users = {row.name for row in eligible_users(AGENT_ROLE)}
	else:
		users = set(frappe.get_all(MEMBER, filters={"thread": thread.name, "active": 1}, pluck="user"))
	for user in users.union(extra):
		frappe.publish_realtime(EVENT, user=user, after_commit=True)


def signal_user():
	frappe.publish_realtime(EVENT, user=frappe.session.user, after_commit=True)


def _clean_text(value, length):
	value = (value or "").strip()
	if len(value) > length:
		frappe.throw(_("Text is too long. The limit is {0} characters.").format(length))
	return value


@frappe.whitelist(allow_guest=True, methods=["GET"])
def bootstrap():
	team = bool(has_role(TEAM_ROLE))
	agent = bool(has_role(AGENT_ROLE) and frappe.db.get_single_value(SETTINGS, "enabled"))
	return {
		"team": team, "whatsapp": agent, "user": frappe.session.user if team or agent else None,
		"csrf": get_csrf_token() if team or agent else None,
		"can_manage_users": bool((team or agent) and frappe.has_permission("User", "write")),
	}


@frappe.whitelist(methods=["GET"])
def users(whatsapp=0):
	role = AGENT_ROLE if cint(whatsapp) else TEAM_ROLE
	require_role(role)
	return eligible_users(role)


@frappe.whitelist(methods=["POST"])
def start_thread(members, title=None, group=0):
	user = require_role(TEAM_ROLE)
	values = frappe.parse_json(members)
	if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
		frappe.throw(_("Choose users from the directory."))
	peers = sorted(set(values) - {user})
	if not peers or len(peers) > 50 or any(not has_role(TEAM_ROLE, peer) for peer in peers):
		frappe.throw(_("Choose between 1 and 50 eligible ERPNext users."))
	title = _clean_text(title, 120)
	if cint(group):
		if not title:
			frappe.throw(_("Enter a group name."))
		thread = insert(THREAD, kind="Group", title=title, manager=user)
		for member in [user, *peers]:
			set_member(thread.name, member)
	else:
		if len(peers) != 1:
			frappe.throw(_("Choose one recipient for a direct message."))
		name = identifier("direct", *sorted([user, peers[0]]))
		if frappe.db.exists(THREAD, name):
			return name
		frappe.db.savepoint("new_chat_thread")
		try:
			thread = insert(THREAD, name, kind="Direct", pair_key=name)
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			frappe.db.rollback(save_point="new_chat_thread")
			return name
		for member in [user, *peers]:
			set_member(name, member)
	changed(thread)
	return thread.name


@frappe.whitelist(methods=["POST"])
def update_group(thread, action, value=None):
	user = require_role(TEAM_ROLE)
	doc = get_thread(thread, lock=True)
	check_thread(doc, user, lock=True)
	if doc.kind != "Group" or (action != "leave" and doc.manager != user):
		deny()
	removed = []
	if action == "rename":
		title = _clean_text(value, 120)
		if not title:
			frappe.throw(_("Enter a group name."))
		frappe.db.set_value(THREAD, thread, "title", title)
	elif action == "add":
		if not has_role(TEAM_ROLE, value) or value in (None, "", user):
			deny()
		if not membership(thread, value, lock=True):
			set_member(thread, value, cint(doc.last_sequence))
	elif action == "transfer":
		if value == user or not membership(thread, value, lock=True) or not has_role(TEAM_ROLE, value):
			deny()
		frappe.db.set_value(THREAD, thread, "manager", value)
	elif action in ("remove", "leave"):
		target = user if action == "leave" else value
		if target == doc.manager:
			frappe.throw(_("Transfer group ownership before leaving."))
		member = membership(thread, target, lock=True)
		if member:
			frappe.db.set_value(MEMBER, member.name, "active", 0)
			removed.append(target)
	else:
		frappe.throw(_("Unknown group action."))
	changed(doc, removed)


def public_thread(doc, user, member=None):
	title = doc.title or doc.peer
	peers = []
	if doc.kind != "WhatsApp":
		peers = frappe.get_all(MEMBER, filters={"thread": doc.name, "active": 1}, pluck="user")
		if doc.kind == "Direct":
			peer = next((entry for entry in peers if entry != user), user)
			title = frappe.get_cached_value("User", peer, "full_name") or peer
	cursor = cint(member.last_read) if member else 0
	unread_filter = {"thread": doc.name, "sequence": (">", max(cursor, cint(member.joined_after) if member else 0))}
	if doc.kind == "WhatsApp":
		unread_filter["direction"] = "Inbound"
	else:
		unread_filter["sender"] = ("!=", user)
	latest = frappe.db.get_value(MESSAGE, unread_filter, ["sequence", "creation"],
		order_by="sequence desc", as_dict=True)
	reply_until = None
	if doc.kind == "WhatsApp" and doc.last_inbound:
		reply_until = (get_datetime(doc.last_inbound).replace(tzinfo=UTC) + timedelta(hours=24)).isoformat()
	return {
		"name": doc.name, "kind": doc.kind, "title": title, "manager": doc.manager,
		"members": peers, "assignee": doc.assignee, "unread": bool(latest),
		"last_read": cursor, "unread_at": latest.creation if latest else None, "updated": doc.modified,
		"reply_until": reply_until, "opted_in": bool(doc.opted_in),
	}


@frappe.whitelist(methods=["GET"])
def thread_info(thread):
	doc = get_thread(thread)
	return public_thread(doc, frappe.session.user, check_thread(doc))


def inbox_threads(user, team, whatsapp):
	threads = []
	if team:
		memberships = frappe.get_all(MEMBER, filters={"user": user, "active": 1}, fields=["*"])
		member_by_thread = {item.thread: item for item in memberships}
		if member_by_thread:
			for doc in frappe.get_all(THREAD, filters={"name": ["in", list(member_by_thread)]}, fields=["*"]):
				threads.append(public_thread(doc, user, member_by_thread[doc.name]))
	if whatsapp:
		memberships = frappe.get_all(MEMBER, filters={"user": user, "active": 1}, fields=["*"])
		member_by_thread = {item.thread: item for item in memberships}
		phone_id = frappe.db.get_single_value(SETTINGS, "phone_number_id")
		for doc in frappe.get_all(THREAD, filters={"kind": "WhatsApp", "business_phone_id": phone_id}, fields=["*"]):
			threads.append(public_thread(doc, user, member_by_thread.get(doc.name)))
	return sorted(threads, key=lambda row: row["updated"], reverse=True)


def safe_record_file(file_id, for_user):
	if not file_id or not frappe.db.exists("File", file_id):
		return None
	file = frappe.get_doc("File", file_id)
	if (
		file.is_folder or file.is_remote_file or not file.attached_to_doctype or not file.attached_to_name
		or file.attached_to_doctype == MESSAGE
		or not frappe.db.exists(file.attached_to_doctype, file.attached_to_name)
		or not frappe.has_permission(file.attached_to_doctype, "read", doc=file.attached_to_name, user=for_user)
		or not file.has_permission("read", user=for_user)
	):
		return None
	return file


@frappe.whitelist(methods=["GET"])
def record_files(doctype, document):
	user = require_role(TEAM_ROLE)
	if not frappe.db.exists(doctype, document) or not frappe.has_permission(doctype, "read", doc=document):
		deny()
	files = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": document}, pluck="name")
	return [{"id": file.name, "label": file.file_name} for name in files if (file := safe_record_file(name, user))]


def public_message(row, user):
	from ask_esafe_ai.ask_esafe_ai.profiles import chat_profile

	result = {key: row.get(key) for key in ("name", "sequence", "sender", "direction", "body", "status", "creation")}
	result["sender_profile"] = chat_profile(row.sender)
	if row.status == "Sending" and now_datetime() - get_datetime(row.modified) > timedelta(minutes=2):
		result["status"] = "Uncertain"
	if row.file_id:
		result["attachment"] = row.file_label
	elif row.record_file:
		file = safe_record_file(row.record_file, user)
		result["attachment"] = file.file_name if file else None
		result["restricted"] = not file
	elif row.media_id:
		result["attachment_pending"] = True
	return result


@frappe.whitelist(methods=["GET"])
def history(thread, before=None, after=None, unread=0):
	doc = get_thread(thread)
	member = check_thread(doc)
	floor = cint(member.joined_after) if member else 0
	filters = [["thread", "=", thread], ["sequence", ">", floor]]
	cursor = cint(member.last_read) if member else 0
	if after is not None or cint(unread):
		start = cint(after) if after is not None else cursor
		rows = frappe.get_all(MESSAGE, filters=[*filters, ["sequence", ">", start]],
			fields=MESSAGE_FIELDS, order_by="sequence asc", limit=51)
		if rows or after is not None:
			return {"messages": [public_message(row, frappe.session.user) for row in rows[:50]],
				"more_after": len(rows) > 50, "more": start > floor}
	if before:
		filters.append(["sequence", "<", cint(before)])
	rows = frappe.get_all(MESSAGE, filters=filters, fields=MESSAGE_FIELDS, order_by="sequence desc", limit=51)
	return {"messages": [public_message(row, frappe.session.user) for row in reversed(rows[:50])], "more": len(rows) > 50}


@frappe.whitelist(methods=["POST"])
def mark_read(thread, sequence):
	doc = get_thread(thread, lock=True)
	member = check_thread(doc, lock=True)
	user = frappe.session.user
	cursor = max(0, min(cint(sequence), cint(doc.last_sequence)))
	if not member:
		set_member(thread, user)
		member = membership(thread, user)
	if cursor > cint(member.last_read):
		frappe.db.set_value(MEMBER, member.name, "last_read", cursor)
		signal_user()


def append_message(thread, name=None, **fields):
	sequence = cint(thread.last_sequence) + 1
	doc = insert(MESSAGE, name, thread=thread.name, sequence=sequence, **fields)
	frappe.db.set_value(THREAD, thread.name, "last_sequence", sequence)
	thread.last_sequence = sequence
	return doc


def _cipher():
	return Fernet(get_encryption_key().encode("ascii"))


def store_upload(message, filename, content, content_type=None):
	from frappe.core.api.file import get_max_file_size

	filename = re.sub(r"[\x00-\x1f\x7f]", "", (filename or "").replace("\\", "/").rsplit("/", 1)[-1]).strip()
	if not filename or not content or len(content) > min(FILE_LIMIT, get_max_file_size()):
		frappe.throw(_("Choose a nonempty file within the site upload limit (at most 16 MB)."))
	extension = PurePath(filename).suffix.upper().lstrip(".")
	allowed = frappe.get_system_settings("allowed_file_extensions")
	if allowed and extension not in allowed.splitlines():
		frappe.throw(_("This file type is not allowed on the site."))
	if extension == "PDF":
		from frappe.utils.pdf import pdf_contains_js

		if pdf_contains_js(content):
			frappe.throw(_("This PDF contains unsafe content."))
	# Each payload has a unique encrypted representation. Even a storage URL or
	# native File alias cannot return the original bytes without this API check.
	file = frappe.get_doc({
		"doctype": "File", "file_name": f"{message.name}.bin", "is_private": 1,
		"attached_to_doctype": MESSAGE, "attached_to_name": message.name,
		"content": _cipher().encrypt(content),
	})
	file.flags.skip_file_size_check = True
	request = getattr(frappe.local, "request", None)
	# The original file has passed the site rules. The stored .bin is a generated
	# ciphertext envelope, so the framework's request-only extension check must
	# not apply a second time to that storage filename.
	try:
		frappe.local.request = None
		file.insert(ignore_permissions=True)
	finally:
		frappe.local.request = request
	frappe.db.set_value("File", file.name, "owner", "Administrator", update_modified=False)
	frappe.db.set_value(MESSAGE, message.name, {
		"file_id": file.name, "file_label": filename[:140],
		"file_type": content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream",
		"media_id": None,
	})


@frappe.whitelist(methods=["POST"])
def send(thread, client_id, body="", record_file=None, template=None):
	doc = get_thread(thread, lock=True)
	check_thread(doc, lock=True)
	user = frappe.session.user
	if not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", client_id or ""):
		frappe.throw(_("Invalid message identifier."))
	name = identifier("message", thread, user, client_id)
	if frappe.db.get_value(MESSAGE, name, "name", for_update=True):
		return name
	body = _clean_text(body, 8000)
	upload = frappe.request.files.get("file")
	if not (body or upload or record_file or template):
		frappe.throw(_("Write a message or select a file."))
	if sum(bool(item) for item in (upload, record_file, template)) > 1:
		frappe.throw(_("Choose one attachment or template at a time."))
	if doc.kind == "WhatsApp":
		from ask_esafe_ai.ask_esafe_ai import whatsapp

		if doc.assignee != user or record_file:
			deny()
		if len(body) > (1024 if upload else 4096):
			frappe.throw(_("The message exceeds WhatsApp's text limit."))
		media_type = whatsapp.upload_type(upload.filename) if upload else None
		fields = whatsapp.validate_outbound(doc, template, bool(body), bool(upload))
	else:
		if template:
			deny()
		if record_file and not safe_record_file(record_file, user):
			deny()
		media_type = None
		fields = {"direction": "Internal"}
	message = append_message(doc, name, sender=user, record_file=record_file, **{"body": body, **fields})
	if upload:
		store_upload(message, upload.filename, upload.stream.read(FILE_LIMIT + 1), media_type)
	if doc.kind == "WhatsApp":
		frappe.enqueue(whatsapp.deliver, message_name=name, enqueue_after_commit=True)
	changed(doc)
	return name


@frappe.whitelist(methods=["GET"])
def download(message):
	if not frappe.db.exists(MESSAGE, message):
		deny()
	row = frappe.get_doc(MESSAGE, message)
	member = check_thread(get_thread(row.thread))
	if member and cint(row.sequence) <= cint(member.joined_after):
		deny()
	if row.file_id:
		file = frappe.get_doc("File", row.file_id)
		content = _cipher().decrypt(file.get_content())
		filename = row.file_label
	else:
		file = safe_record_file(row.record_file, frappe.session.user)
		if not file:
			deny()
		content, filename = file.get_content(), file.file_name
	if isinstance(content, str):
		content = content.encode()
	response = send_file(BytesIO(content), frappe.request.environ, download_name=filename,
		mimetype="application/octet-stream", as_attachment=True)
	response.headers["Cache-Control"] = "private, no-store"
	return response


def notifications(user):
	rows = frappe.get_all(
		"Notification Log", filters={"for_user": user},
		fields=["name", "title", "subject", "description", "document_type", "document_name", "read", "creation"],
		order_by="read asc, creation desc", limit=50,
	)
	for row in rows:
		row.title = strip_html(row.title or row.subject or _("ERPNext notification"))
		row.description = strip_html(row.description or "")
		row.pop("subject", None)
		row.url = None
		if row.document_type and row.document_name:
			if frappe.db.exists(row.document_type, row.document_name) and frappe.has_permission(
				row.document_type, "read", doc=row.document_name, user=user,
			):
				from frappe.utils import get_url_to_form

				row.url = get_url_to_form(row.document_type, row.document_name)
			else:
				row.title = _("ERPNext notification")
				row.description = ""
		row.pop("document_type", None)
		row.pop("document_name", None)
	return rows


@frappe.whitelist(methods=["GET"])
def overview():
	user = frappe.session.user
	team = has_role(TEAM_ROLE)
	agent = has_role(AGENT_ROLE) and frappe.db.get_single_value(SETTINGS, "enabled")
	if not (team or agent):
		deny()
	return {
		"threads": inbox_threads(user, team, agent), "notifications": notifications(user),
		"erp_unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0}),
	}


@frappe.whitelist(methods=["POST"])
def read_notification(name):
	if not (has_role(TEAM_ROLE) or (has_role(AGENT_ROLE) and frappe.db.get_single_value(SETTINGS, "enabled"))):
		deny()
	from frappe.desk.doctype.notification_log.notification_log import mark_as_read

	mark_as_read(name)
	signal_user()
