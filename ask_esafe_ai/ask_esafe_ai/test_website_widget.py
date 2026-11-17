import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ask_esafe_ai.ask_esafe_ai import website_widget


class Response:
	def __init__(self, html="<html><body>POS</body></html>", mimetype="text/html"):
		self.html = html
		self.mimetype = mimetype
		self.status_code = 200
		self.is_streamed = False
		self.direct_passthrough = False
		self.headers = {"ETag": "old"}

	def get_data(self, as_text=False):
		return self.html

	def set_data(self, html):
		self.html = html


class TestWebsiteWidget(unittest.TestCase):
	def inject(self, response, path="/pos", method="GET", user="test@example.com"):
		with patch.object(website_widget, "frappe", SimpleNamespace(session=SimpleNamespace(user=user))):
			website_widget.inject_widget(response, SimpleNamespace(path=path, method=method))

	def test_custom_html_injected_once_and_not_shared_cached(self):
		response = Response()
		self.inject(response)
		self.inject(response)
		self.assertEqual(response.html.count(website_widget.ASSET), 1)
		self.assertEqual(response.headers["Cache-Control"], "private, no-store")
		self.assertNotIn("ETag", response.headers)

	def test_guests_desk_api_login_and_non_html_are_unchanged(self):
		for path, method, user in [
			("/pos", "GET", "Guest"), ("/desk", "GET", "Administrator"),
			("/desk/setup/home", "GET", "Administrator"), ("/app/home", "GET", "Administrator"),
			("/api/method/test", "GET", "Administrator"), ("/login", "GET", "Administrator"),
			("/pos", "POST", "Administrator"),
		]:
			with self.subTest(path=path, method=method, user=user):
				response = Response()
				self.inject(response, path, method, user)
				self.assertNotIn(website_widget.ASSET, response.html)
		response = Response(mimetype="application/json")
		self.inject(response)
		self.assertNotIn(website_widget.ASSET, response.html)

	def test_template_hook_script_is_not_duplicated(self):
		response = Response(f'<body><script src="{website_widget.ASSET}"></script></body>')
		before = response.html
		self.inject(response)
		self.assertEqual(response.html, before)

	def test_streams_errors_compressed_and_fragments_are_not_modified(self):
		for field, value in [("is_streamed", True), ("direct_passthrough", True), ("status_code", 403)]:
			response = Response()
			setattr(response, field, value)
			self.inject(response)
			self.assertNotIn(website_widget.ASSET, response.html)
		for header, value in [("Content-Encoding", "gzip"), ("Content-Disposition", "attachment")]:
			response = Response()
			response.headers[header] = value
			self.inject(response)
			self.assertNotIn(website_widget.ASSET, response.html)
		response = Response("<section>HTML fragment</section>")
		self.inject(response)
		self.assertNotIn(website_widget.ASSET, response.html)
		response = Response()
		response.headers["Content-Encoding"] = "gzip"
		self.inject(response)
		self.assertNotIn(website_widget.ASSET, response.html)
		response = Response("<div>fragment</div>")
		self.inject(response)
		self.assertEqual(response.html, "<div>fragment</div>")
