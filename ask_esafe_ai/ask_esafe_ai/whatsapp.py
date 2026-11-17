from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from urllib.parse import urlsplit

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime
from werkzeug.wrappers import Response

from ask_esafe_ai.ask_esafe_ai import messaging as chat

MIME_TYPES = {
	".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
	".pdf": "application/pdf", ".txt": "text/plain",
	".doc": "application/msword", ".xls": "application/vnd.ms-excel",
	".ppt": "application/vnd.ms-powerpoint",
	".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
EXTENSIONS = {mime: ext for ext, mime in MIME_TYPES.items()}
STATUS_ORDER = {"Queued": 0, "Sending": 1, "Uncertain": 2, "Sent": 3, "Delivered": 4, "Read": 5}
PROVIDER_STATUS = {"sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed"}


def configuration(require_enabled=True):
	settings = frappe.get_single(chat.SETTINGS)
	credentials = {
		field: settings.get_password(field, raise_exception=False)
		for field in ("access_token", "app_secret", "verify_token")
	}
	if (
		(require_enabled and not settings.enabled) or not re.fullmatch(r"\d+", settings.phone_number_id or "")
		or not re.fullmatch(r"v\d+\.\d+", settings.api_version or "") or not all(credentials.values())
	):
		frappe.throw(_("Configure the WhatsApp Business connection before enabling the inbox."))
	return settings, credentials


def upload_type(filename):
	mime = MIME_TYPES.get(PurePath(filename or "").suffix.lower())
	if not mime:
		frappe.throw(_("Choose a supported photo or document for WhatsApp."))
	return mime


def utc_now():
	return datetime.now(UTC).replace(tzinfo=None)


def reply_open(thread):
	return bool(thread.last_inbound and (utc_now() - get_datetime(thread.last_inbound)) < timedelta(hours=24))


def templates(settings):
	return [
		item.strip() for item in (settings.approved_templates or "").splitlines()
		if re.fullmatch(r"[a-z0-9_]+:[a-zA-Z_]+", item.strip())
	]


@frappe.whitelist(methods=["GET"])
def composer(thread):
	doc = chat.get_thread(thread)
	chat.check_thread(doc)
	if doc.kind != "WhatsApp":
		chat.deny()
	settings, _credentials = configuration()
	return {
		"open": reply_open(doc), "opted_in": bool(doc.opted_in),
		"templates": templates(settings) if doc.opted_in else [],
	}


@frappe.whitelist(methods=["POST"])
def assign(thread, agent=None):
	user = chat.require_role(chat.AGENT_ROLE)
	doc = chat.get_thread(thread, lock=True)
	chat.check_thread(doc)
	if doc.kind != "WhatsApp" or (doc.assignee and doc.assignee != user):
		chat.deny()
	if not chat.has_role(chat.AGENT_ROLE, agent or user):
		chat.deny()
	frappe.db.set_value(chat.THREAD, thread, "assignee", agent or user)
	chat.changed(doc)


@frappe.whitelist(methods=["POST"])
def record_consent(thread, granted):
	user = chat.require_role(chat.AGENT_ROLE)
	doc = chat.get_thread(thread, lock=True)
	chat.check_thread(doc)
	if doc.kind != "WhatsApp" or doc.assignee != user:
		chat.deny()
	frappe.db.set_value(chat.THREAD, thread, "opted_in", int(str(granted) == "1"))
	chat.changed(doc)


def validate_outbound(thread, template, body, upload):
	settings, _credentials = configuration()
	fields = {"direction": "Outbound", "status": "Queued"}
	if template:
		if body or upload or not thread.opted_in or template not in templates(settings):
			frappe.throw(_("Choose an approved template for a customer who has opted in."))
		fields["template"], fields["template_language"] = template.split(":")
		fields["body"] = _("Template: {0}").format(fields["template"])
	elif not reply_open(thread):
		frappe.throw(_("The WhatsApp reply window is closed. Choose an approved template."))
	return fields


def graph_request(settings, credentials, endpoint, *, method="GET", **kwargs):
	return requests.request(
		method, f"https://graph.facebook.com/{settings.api_version}/{endpoint}",
		headers={"Authorization": f"Bearer {credentials['access_token']}"},
		timeout=(5, 25), allow_redirects=False, **kwargs,
	)


def _media_payload(settings, creds, message):
	file = frappe.get_doc("File", message.file_id)
	content = chat._cipher().decrypt(file.get_content())
	kind = "image" if message.file_type.startswith("image/") else "document"
	if kind == "image" and len(content) > 5 * 1024 * 1024:
		raise ValueError("Image exceeds WhatsApp limit")
	response = graph_request(
		settings, creds, f"{settings.phone_number_id}/media", method="POST",
		data={"messaging_product": "whatsapp", "type": message.file_type},
		files={"file": (message.file_label, content, message.file_type)},
	)
	response.raise_for_status()
	media = {"id": response.json()["id"]}
	if message.body:
		media["caption"] = message.body
	if kind == "document":
		media["filename"] = message.file_label
	return {"type": kind, kind: media}


def deliver(message_name):
	thread = chat.get_thread(frappe.db.get_value(chat.MESSAGE, message_name, "thread"), lock=True)
	message = frappe.get_doc(chat.MESSAGE, message_name, for_update=True)
	if message.status != "Queued":
		return
	if thread.assignee != message.sender or not chat.has_role(chat.AGENT_ROLE, message.sender):
		set_delivery(message, thread, "Failed")
		return
	if (message.template and not thread.opted_in) or (not message.template and not reply_open(thread)):
		set_delivery(message, thread, "Failed")
		return
	frappe.db.set_value(chat.MESSAGE, message.name, "status", "Sending")
	frappe.db.commit()
	try:
		settings, creds = configuration()
		if thread.business_phone_id != settings.phone_number_id:
			raise ValueError("The business phone number changed")
		if message.template:
			if f"{message.template}:{message.template_language}" not in templates(settings):
				raise ValueError("Template is no longer configured")
			payload = {"type": "template", "template": {
				"name": message.template, "language": {"code": message.template_language},
			}}
		elif message.file_id:
			payload = _media_payload(settings, creds, message)
		else:
			payload = {"type": "text", "text": {"body": message.body}}
	except (requests.RequestException, KeyError, ValueError, frappe.ValidationError):
		set_delivery(message, thread, "Failed")
		return
	try:
		response = graph_request(
			settings, creds, f"{settings.phone_number_id}/messages", method="POST",
			json={
				"messaging_product": "whatsapp", "to": thread.peer, **payload,
				"biz_opaque_callback_data": message.name,
			},
		)
		if response.status_code >= 500:
			set_delivery(message, thread, "Uncertain")
		elif not response.ok:
			set_delivery(message, thread, "Failed")
		else:
			set_delivery(message, thread, "Sent", response.json()["messages"][0]["id"])
	except (requests.RequestException, ValueError, KeyError, IndexError):
		set_delivery(message, thread, "Uncertain")


def set_delivery(message, thread, status, provider_id=None):
	row = frappe.get_doc(chat.MESSAGE, message.name, for_update=True)
	if row.status == status and not provider_id:
		return
	if row.status in ("Delivered", "Read") and STATUS_ORDER.get(status, -1) <= STATUS_ORDER[row.status]:
		return
	if row.status == "Sent" and status == "Uncertain":
		return
	if row.status == "Failed" and status in ("Sent", "Uncertain") and not provider_id:
		return
	fields = {"status": status}
	if provider_id:
		fields["provider_id"] = provider_id
	frappe.db.set_value(chat.MESSAGE, row.name, fields)
	chat.changed(thread)


def recover_queued_messages():
	if not frappe.db.get_single_value(chat.SETTINGS, "enabled"):
		return
	for name in frappe.get_all(chat.MESSAGE, filters={"status": "Queued", "direction": "Outbound"},
		pluck="name", order_by="creation asc", limit=100):
		frappe.enqueue(deliver, message_name=name)


def receive_media(message_name):
	message = frappe.get_doc(chat.MESSAGE, message_name, for_update=True)
	if message.file_id or not message.media_id:
		return
	thread = chat.get_thread(message.thread)
	try:
		settings, creds = configuration()
		metadata = graph_request(settings, creds, message.media_id, params={"phone_number_id": settings.phone_number_id})
		metadata.raise_for_status()
		media = metadata.json()
		url = urlsplit(media["url"])
		if url.scheme != "https" or url.hostname not in ("lookaside.fbsbx.com", "lookaside.facebook.com"):
			raise ValueError("Unexpected WhatsApp media host")
		mime = media["mime_type"]
		limit = min(chat.FILE_LIMIT, 5 * 1024 * 1024) if mime.startswith("image/") else chat.FILE_LIMIT
		if mime not in EXTENSIONS or int(media.get("file_size", 0)) > limit:
			raise ValueError("Unsupported WhatsApp attachment")
		with requests.get(media["url"], headers={"Authorization": f"Bearer {creds['access_token']}"},
						timeout=(5, 25), stream=True, allow_redirects=False) as response:
			response.raise_for_status()
			if response.is_redirect:
				raise ValueError("Unexpected WhatsApp media redirect")
			data = bytearray()
			for chunk in response.iter_content(65536):
				data.extend(chunk)
				if len(data) > limit:
					raise ValueError("WhatsApp attachment too large")
		chat.store_upload(message, message.file_label or f"WhatsApp attachment{EXTENSIONS[mime]}", bytes(data), mime)
	except (requests.RequestException, KeyError, ValueError, frappe.ValidationError):
		frappe.db.set_value(chat.MESSAGE, message.name, {"media_id": None, "body": message.body or _("Attachment unavailable")})
	chat.changed(thread)


def incoming(phone_id, message, display_name):
	peer = message.get("from", "")
	provider_id = message.get("id", "")
	if not re.fullmatch(r"\d{5,20}", peer) or not provider_id:
		return
	name = chat.identifier("whatsapp", phone_id, peer)
	if not frappe.db.exists(chat.THREAD, name):
		frappe.db.savepoint("whatsapp_thread")
		try:
			chat.insert(chat.THREAD, name, kind="WhatsApp", pair_key=name, peer=peer,
				business_phone_id=phone_id, title=(display_name or peer)[:120])
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			frappe.db.rollback(save_point="whatsapp_thread")
	thread = chat.get_thread(name, lock=True)
	if frappe.db.get_value(chat.MESSAGE, {"provider_id": provider_id}, "name", for_update=True):
		return
	kind = message.get("type")
	media = message.get(kind, {}) if kind in ("image", "document") else {}
	text = message.get("text", {}).get("body") if kind == "text" else media.get("caption")
	row = chat.append_message(
		thread, provider_id=provider_id, direction="Inbound",
		body=(text or ("" if media else _("Unsupported WhatsApp message")))[:8000],
		media_id=media.get("id"), file_label=(media.get("filename") or "")[:140],
	)
	received = datetime.fromtimestamp(int(message.get("timestamp") or 0), UTC).replace(tzinfo=None)
	received = min(received, utc_now())
	if not thread.last_inbound or received > get_datetime(thread.last_inbound):
		frappe.db.set_value(chat.THREAD, thread.name, "last_inbound", received)
	if row.media_id:
		frappe.enqueue(receive_media, message_name=row.name, enqueue_after_commit=True)
	chat.changed(thread)


def delivery_callback(event):
	provider_id = event.get("id")
	status = PROVIDER_STATUS.get(event.get("status"))
	if not status or not provider_id:
		return
	name = frappe.db.get_value(chat.MESSAGE, {"provider_id": provider_id}, "name")
	name = name or event.get("biz_opaque_callback_data")
	if name and frappe.db.exists(chat.MESSAGE, name):
		message = frappe.get_doc(chat.MESSAGE, name)
		thread = chat.get_thread(message.thread)
		if message.direction == "Outbound" and thread.kind == "WhatsApp":
			set_delivery(message, thread, status, provider_id)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def webhook():
	request = frappe.request
	settings, creds = configuration(require_enabled=request.method != "GET")
	if request.method == "GET":
		if request.args.get("hub.mode") == "subscribe" and hmac.compare_digest(
			request.args.get("hub.verify_token", "").encode(), creds["verify_token"].encode(),
		):
			return Response(request.args.get("hub.challenge", ""), content_type="text/plain")
		return Response("Forbidden", status=403)
	body = request.get_data(cache=True)
	expected = "sha256=" + hmac.new(creds["app_secret"].encode(), body, hashlib.sha256).hexdigest()
	actual = request.headers.get("X-Hub-Signature-256", "")
	if not hmac.compare_digest(expected.encode(), actual.encode()):
		return Response("Forbidden", status=403)
	if len(body) > 2 * 1024 * 1024:
		return Response("Request too large", status=413)
	payload = request.get_json()
	if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
		return Response("Invalid notification", status=400)
	for entry in payload.get("entry", []):
		for change in entry.get("changes", []):
			if change.get("field") != "messages":
				continue
			value = change.get("value", {})
			if value.get("metadata", {}).get("phone_number_id") != settings.phone_number_id:
				continue
			contacts = {row["wa_id"]: row.get("profile", {}).get("name") for row in value.get("contacts", [])}
			for message in value.get("messages", []):
				incoming(settings.phone_number_id, message, contacts.get(message.get("from")))
			for status in value.get("statuses", []):
				delivery_callback(status)
	return Response("OK", content_type="text/plain")
