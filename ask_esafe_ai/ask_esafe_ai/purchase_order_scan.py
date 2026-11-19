import json
from pathlib import Path

import frappe
from frappe import _

SKILL_NAME = "purchase-orders-from-scans"
SKILL_TITLE = "Create Purchase Orders from scans"
BUILTIN_SKILLS = (
	{
		"name": "customer-account-summary",
		"title": "Customer Account Summary",
		"file": "customer_account_summary.md",
		"roles": ("System Manager", "Sales Manager", "Sales User", "Accounts Manager", "Accounts User"),
	},
	{
		"name": "sales-insights",
		"title": "Sales Insights",
		"file": "sales_insights.md",
		"roles": ("System Manager", "Sales Manager", "Sales User"),
	},
	{
		"name": "stock-availability",
		"title": "Stock Availability",
		"file": "stock_availability.md",
		"roles": ("System Manager", "Stock Manager", "Stock User", "Sales Manager", "Sales User", "Purchase Manager", "Purchase User"),
	},
	{
		"name": "projects-and-tasks",
		"title": "Projects and Tasks",
		"file": "projects_and_tasks.md",
		"roles": ("System Manager", "Projects Manager", "Projects User"),
	},
)


def install_skill():
	"""Install built-in skills once while preserving site edits."""
	if not frappe.db.exists("DocType", "ASK ESAFE AI Skill"):
		return
	definitions = (
		{
			"name": SKILL_NAME,
			"title": SKILL_TITLE,
			"file": "purchase_orders_from_scans.md",
			"roles": ("System Manager", "Purchase Manager", "Purchase User"),
		},
		*BUILTIN_SKILLS,
	)
	for skill in definitions:
		if frappe.db.exists("ASK ESAFE AI Skill", skill["name"]):
			continue
		roles = [{"role": role} for role in skill["roles"] if frappe.db.exists("Role", role)]
		description = Path(__file__).resolve().parents[1].joinpath("skills", skill["file"]).read_text(
			encoding="utf-8",
		)
		frappe.get_doc({
			"doctype": "ASK ESAFE AI Skill", "title": skill["title"], "description": description, "roles": roles,
		}).insert(ignore_permissions=True, set_name=skill["name"])


def _scan_context():
	from ask_esafe_ai.ask_esafe_ai.api import can_access_ask_esafe_ai

	if not can_access_ask_esafe_ai():
		frappe.throw(_("You do not have access to ASK ESAFE AI."), frappe.PermissionError)
	roles = frappe.get_all(
		"Has Role",
		filters={"parent": SKILL_NAME, "parenttype": "ASK ESAFE AI Skill", "parentfield": "roles"},
		pluck="role",
	) if frappe.db.exists("ASK ESAFE AI Skill", SKILL_NAME) else []
	allowed = bool(set(roles).intersection(frappe.get_roles()))
	settings = {
		field: frappe.db.get_single_value("ASK ESAFE AI Settings", field)
		for field in (
			"enabled", "allow_file_upload", "allow_agent_mode", "model",
			"vision_model_is_chat_model", "vision_model",
		)
	}
	reason = ""
	if not frappe.db.exists("DocType", "Purchase Order"):
		reason = _("Install ERPNext to create Purchase Orders.")
	elif not frappe.has_permission("Purchase Order", "create"):
		reason = _("You need permission to create Purchase Orders.")
	elif not allowed:
		reason = _("Ask your System Manager to enable the purchase-order scanning skill for your role.")
	elif not settings["enabled"]:
		reason = _("Enable ASK ESAFE AI in Settings.")
	elif not settings["allow_file_upload"]:
		reason = _("Enable Allow File Upload in ASK ESAFE AI Settings.")
	elif not settings["allow_agent_mode"]:
		reason = _("Enable Allow Agent Mode in ASK ESAFE AI Settings to prepare draft Purchase Orders.")
	elif not settings["model"]:
		reason = _("Configure the chat model in ASK ESAFE AI Settings.")
	elif not (settings["model"] if settings["vision_model_is_chat_model"] else settings["vision_model"]):
		reason = _("Configure a vision model in ASK ESAFE AI Settings to scan documents.")
	skill_doc = None
	if frappe.db.exists("ASK ESAFE AI Skill", SKILL_NAME) and frappe.has_permission("ASK ESAFE AI Skill", "write"):
		skill_doc = frappe.get_doc("ASK ESAFE AI Skill", SKILL_NAME)
	return {
		"ready": not reason, "reason": reason, "skill": SKILL_NAME,
		"can_manage": bool(skill_doc),
	}


@frappe.whitelist(methods=["GET"])
def get_context():
	return _scan_context()


@frappe.whitelist(methods=["GET"])
def list_available_skills():
	from ask_esafe_ai.ask_esafe_ai.api import can_access_ask_esafe_ai
	from ask_esafe_ai.ask_esafe_ai.skill_utils import get_accessible_skill_doc, get_available_skill_summaries

	if not can_access_ask_esafe_ai():
		frappe.throw(_("You do not have access to ASK ESAFE AI."), frappe.PermissionError)

	result = []
	for summary in get_available_skill_summaries():
		skill = get_accessible_skill_doc(summary["name"])
		result.append({"name": skill.name, "title": skill.title, "description": skill.description or ""})
	return sorted(result, key=lambda item: (item["name"] != SKILL_NAME, item["title"].casefold()))


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
