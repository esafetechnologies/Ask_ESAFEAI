(() => {
	"use strict";
	if (window.askEsafeWebsiteWidget || window.parent !== window || /^\/(desk|app)(\/|$)/.test(location.pathname)) return;
	window.askEsafeWebsiteWidget = true;
	const asset = "/assets/ask_esafe_ai/";

	async function mount() {
		const response = await fetch("/api/method/ask_esafe_ai.api.get_ask_esafe_ai_boot_payload", {
			credentials: "same-origin", cache: "no-store",
		});
		if (!response.ok) return;
		const { message: access } = await response.json();
		if (!access?.allowed) return;
		const style = document.createElement("link");
		style.rel = "stylesheet";
		style.href = asset + "css/website_widget.css";
		document.head.append(style);
		const root = document.createElement("div");
		root.id = "ask-esafe-ai-website";
		root.innerHTML = `<button type="button" class="esafe-launcher" aria-label="Open ASK ESAFE AI" aria-expanded="false">
			<img src="${asset}img/esafe-ai-emblem.svg" alt=""></button>
			<section class="esafe-website-panel" aria-label="ASK ESAFE AI" hidden>
				<div class="esafe-load-status" role="status">Loading ASK ESAFE AI...</div>
				<button type="button" class="esafe-website-close" aria-label="Close ASK ESAFE AI">&times;</button>
			</section>`;
		document.body.append(root);
		const launcher = root.querySelector(".esafe-launcher");
		const panel = root.querySelector("section");
		const status = root.querySelector(".esafe-load-status");
		const close = root.querySelector(".esafe-website-close");
		let frame, deadline, widget;

		function updateContext() {
			if (frame?.contentWindow) {
				// Only page identity is shared; never scrape POS customer/payment data.
				frame.contentWindow.askEsafeHostContext = {
					route: location.pathname + location.hash,
					route_parts: [location.pathname, location.hash],
				};
			}
		}

		function hide() {
			panel.hidden = true;
			launcher.hidden = false;
			launcher.setAttribute("aria-expanded", "false");
			launcher.focus();
		}

		function connect() {
			try {
				const doc = frame.contentDocument;
				if (doc?.head && !doc.getElementById("ask-esafe-ai-frame-style")) {
					const css = doc.createElement("link");
					css.id = "ask-esafe-ai-frame-style";
					css.rel = "stylesheet";
					css.href = asset + "css/website_widget_frame.css";
					doc.head.append(css);
				}
				widget = frame.contentWindow?.ask_esafe_aiWidget;
				if (!widget?.initialized || !doc.getElementById("ask-esafe-ai-frame-style")?.sheet) {
					throw new Error("Waiting for assistant");
				}
				updateContext();
				frame.hidden = false;
				widget.toggle(true);
				status.hidden = true;
				frame.contentWindow.addEventListener("keydown", (event) => {
					if (event.key === "Escape" && !doc.querySelector('.modal.show')) hide();
				});
			} catch {
				if (Date.now() < deadline) { setTimeout(connect, 250); return; }
				status.textContent = "The assistant could not load. Check your login and access, then close and reopen to retry.";
				frame.remove();
				frame = widget = null;
			}
		}

		launcher.addEventListener("click", () => {
			panel.hidden = false;
			launcher.hidden = true;
			launcher.setAttribute("aria-expanded", "true");
			close.focus();
			if (!frame) {
				status.hidden = false;
				status.textContent = "Loading ASK ESAFE AI...";
				frame = document.createElement("iframe");
				frame.title = "ASK ESAFE AI assistant";
				frame.hidden = true;
				frame.src = "/desk";
				panel.append(frame);
				deadline = Date.now() + 45000;
				connect();
			} else if (widget?.initialized) {
				updateContext();
				widget.toggle(true);
			}
		});
		close.addEventListener("click", hide);
		root.addEventListener("keydown", (event) => { if (event.key === "Escape") hide(); });
		window.addEventListener("hashchange", updateContext);
		window.addEventListener("popstate", updateContext);
	}

	const start = () => void mount().catch(() => console.warn("ASK ESAFE AI could not load on this page."));
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
	else start();
})();
