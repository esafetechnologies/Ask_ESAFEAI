import frappe
from frappe.model.document import Document


class ASKESAFEAIChatMessage(Document):
	pass


def on_doctype_update():
	frappe.db.add_unique("ASK ESAFE AI Chat Message", ["thread", "sequence"])
