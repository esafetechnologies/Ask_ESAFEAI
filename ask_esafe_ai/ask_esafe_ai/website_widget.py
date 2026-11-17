"""Include the assistant on custom HTML apps that bypass website template hooks."""

import re

import frappe


ASSET = "/assets/ask_esafe_ai/js/website_widget.js"
SCRIPT = f'<script defer src="{ASSET}" data-ask-esafe-ai-widget></script>'
EXCLUDED_ROUTES = ("/desk", "/app", "/api", "/login", "/update-password", "/assets")


def inject_widget(response=None, request=None):
	if response is None or request is None or request.method != "GET":
		return
	if response.status_code != 200 or response.is_streamed or response.direct_passthrough:
		return
	if response.mimetype != "text/html" or response.headers.get("Content-Encoding"):
		return
	if frappe.session.user == "Guest":
		return
	path = request.path.rstrip("/")
	if any(path == route or path.startswith(route + "/") for route in EXCLUDED_ROUTES):
		return

	html = response.get_data(as_text=True)
	if ASSET in html or not re.search(r"</body\s*>", html, re.IGNORECASE):
		return
	response.set_data(re.sub(r"</body\s*>", SCRIPT + "</body>", html, count=1, flags=re.IGNORECASE))
	# A signed-in page containing the launcher must not be shared with another session.
	response.headers["Cache-Control"] = "private, no-store"
	response.headers.pop("ETag", None)
