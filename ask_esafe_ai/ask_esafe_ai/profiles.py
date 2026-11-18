import frappe


def chat_profile(user):
	"""Public display fields only, returned after the caller checks chat access."""
	if not user or user == "Guest":
		return {}
	profile = frappe.get_cached_value("User", user, ["full_name", "user_image"], as_dict=True) or {}
	return {"full_name": profile.get("full_name") or user, "user_image": profile.get("user_image") or ""}
