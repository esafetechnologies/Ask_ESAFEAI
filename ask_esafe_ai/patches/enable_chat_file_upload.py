import frappe


def execute():
	"""Enable the chat attachment control on existing sites during this rollout."""
	frappe.db.set_single_value("ASK ESAFE AI Settings", "allow_file_upload", 1)
