import json
from pathlib import Path

import frappe
from frappe import _

SKILL_NAME = "purchase-orders-from-scans"
SKILL_TITLE = "Create Purchase Orders from scans"


def install_skill():
	"""Install the built-in skill once while preserving site edits."""
	if not frappe.db.exists("DocType", "ASK ESAFE AI Skill"):
		return
	if frappe.db.exists("ASK ESAFE AI Skill", SKILL_NAME):
		return
	roles = [
		{"role": role} for role in ("System Manager", "Purchase Manager", "Purchase User")
		if frappe.db.exists("Role", role)
	]
	description = Path(__file__).resolve().parents[1].joinpath("skills", "purchase_orders_from_scans.md").read_text(
		encoding="utf-8"
	)
	frappe.get_doc({
		"doctype": "ASK ESAFE AI Skill", "title": SKILL_TITLE, "description": description, "roles": roles,
	}).insert(ignore_permissions=True, set_name=SKILL_NAME)


def _scan_context():
	from ask_esafe_ai.ask_esafe_ai.api import can_access_ask_esafe_ai
	from ask_esafe_ai.ask_esafe_ai.tools import get_settings

	if not can_access_ask_esafe_ai():
		frappe.throw(_("You do not have access to ASK ESAFE AI."), frappe.PermissionError)
	settings = get_settings()
	skill = frappe.get_doc("ASK ESAFE AI Skill", SKILL_NAME) if frappe.db.exists("ASK ESAFE AI Skill", SKILL_NAME) else None
	allowed = bool(skill and {row.role for row in skill.roles}.intersection(frappe.get_roles()))
	reason = ""
	if not frappe.db.exists("DocType", "Purchase Order"):
		reason = _("Install ERPNext to create Purchase Orders.")
	elif not frappe.has_permission("Purchase Order", "create"):
		reason = _("You need permission to create Purchase Orders.")
	elif not allowed:
		reason = _("Ask your System Manager to enable the purchase-order scanning skill for your role.")
	elif not settings.enabled:
		reason = _("Enable ASK ESAFE AI in Settings.")
	elif not settings.allow_file_upload:
		reason = _("Enable Allow File Upload in ASK ESAFE AI Settings.")
	elif not settings.allow_agent_mode:
		reason = _("Enable Allow Agent Mode in ASK ESAFE AI Settings to prepare draft Purchase Orders.")
	elif not settings.model:
		reason = _("Configure the chat model in ASK ESAFE AI Settings.")
	elif not (settings.model if settings.vision_model_is_chat_model else settings.vision_model):
		reason = _("Configure a vision model in ASK ESAFE AI Settings to scan documents.")
	return {
		"ready": not reason, "reason": reason, "skill": SKILL_NAME,
		"can_manage": bool(skill and frappe.has_permission("ASK ESAFE AI Skill", "write", doc=skill)),
	}


@frappe.whitelist(methods=["GET"])
def get_context():
	return _scan_context()


@frappe.whitelist(methods=["POST"])
def prepare_scan(file_id: str, conversation: str):
	from ask_esafe_ai.ask_esafe_ai.skill_utils import get_accessible_skill_doc

	context = _scan_context()
	if not context["ready"]:
		frappe.throw(context["reason"], frappe.PermissionError)
	get_accessible_skill_doc(SKILL_NAME)
	doc = frappe.get_doc("ASK ESAFE AI Conversation", conversation)
	doc.check_permission("write")
	file = frappe.get_doc("File", file_id)
	file.check_permission("read")
	if file.attached_to_doctype != doc.doctype or file.attached_to_name != doc.name:
		frappe.throw(_("Upload this document to the current conversation first."), frappe.PermissionError)
	if Path(file.file_name or "").suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png"}:
		frappe.throw(_("Choose a PDF, JPG, or PNG document."))
	return {
		"message": (
			f"Read the skill {json.dumps(SKILL_NAME)} using read_skill, then follow it to prepare a draft "
			f"Purchase Order from the attached File ID {json.dumps(file.name)}. "
			"Extract the document with extract_document_data, resolve permitted ERPNext records, and "
			"show the extracted details for review. Ask me about missing or uncertain values before "
			"proposing creation. Use the normal confirmation control to create the draft."
		),
	}
