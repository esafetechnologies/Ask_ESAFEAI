import frappe
from frappe.model.document import Document


class ASKESAFEAIChatMember(Document):
	pass


def on_doctype_update():
	frappe.db.add_index("ASK ESAFE AI Chat Member", ["user", "active"])
	frappe.db.add_unique("ASK ESAFE AI Chat Member", ["thread", "user"])
