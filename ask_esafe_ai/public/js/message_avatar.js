export function createMessageAvatar(profile = {}, { assistant = false } = {}) {
	const avatar = document.createElement("span");
	avatar.className = "esafe-message-avatar";
	const label = assistant ? "ASK ESAFE AI" : (profile.full_name || "").trim() || "User";
	avatar.title = label;
	avatar.setAttribute("role", "img");
	avatar.setAttribute("aria-label", label);
	avatar.textContent = assistant ? "e" : label.trim().split(/\s+/u).slice(0, 2)
		.map((part) => Array.from(part)[0] || "").join("").toLocaleUpperCase();
	const source = assistant ? "/assets/ask_esafe_ai/img/esafe-ai-emblem.svg" : profile.user_image;
	if (source) {
		try {
			const url = new URL(source, location.origin);
			// Only load site-hosted profile photos; message content cannot trigger remote image requests.
			if (url.origin === location.origin && /^https?:$/.test(url.protocol)) {
				const image = document.createElement("img");
				image.src = url.href;
				image.alt = "";
				image.addEventListener("error", () => image.remove(), { once: true });
				avatar.append(image);
			}
		} catch { /* Invalid photos keep the initials fallback. */ }
	}
	return avatar;
}
