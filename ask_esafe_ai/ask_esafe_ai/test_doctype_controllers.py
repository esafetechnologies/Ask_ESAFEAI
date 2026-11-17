import importlib
import json
from pathlib import Path

from frappe.model.document import Document, get_controller
from frappe.tests import UnitTestCase


class UnitTestDocTypeControllers(UnitTestCase):
	def test_every_standard_doctype_loads_its_case_sensitive_controller(self):
		doctype_directory = Path(__file__).with_name("doctype")
		for metadata_path in sorted(doctype_directory.glob("*/*.json")):
			metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
			if metadata.get("doctype") != "DocType" or metadata.get("custom"):
				continue
			doctype = metadata["name"]
			classname = doctype.replace(" ", "").replace("-", "")
			module_name = ".".join((
				"ask_esafe_ai.ask_esafe_ai.doctype",
				metadata_path.parent.name,
				metadata_path.stem,
			))
			with self.subTest(doctype=doctype):
				module = importlib.import_module(module_name)
				expected = getattr(module, classname)
				self.assertTrue(issubclass(expected, Document))
				self.assertTrue(issubclass(get_controller(doctype), expected))
