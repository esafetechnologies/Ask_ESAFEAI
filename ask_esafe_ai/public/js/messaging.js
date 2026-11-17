(() => {
	"use strict";

	const asset = "/assets/ask_esafe_ai/";
	const server = "/api/method/ask_esafe_ai.ask_esafe_ai.";
	const translate = (text) => typeof window.__ === "function" ? window.__(text) : text;
	const tabs = { messages: "Messages", notifications: "Notifications", whatsapp: "WhatsApp" };

	function element(tag, className = "", text = "") {
		const node = document.createElement(tag);
		node.className = className;
		node.textContent = text;
		return node;
	}

	function button(text, action, className = "") {
		const node = element("button", className, translate(text));
		node.type = "button";
		node.addEventListener("click", action);
		return node;
	}

	function label(text, control) {
		const node = element("label", "esafe-messaging-field", translate(text));
		node.append(control);
		return node;
	}

	function select(options) {
		const node = element("select");
		for (const [value, text] of options) {
			const option = element("option", "", text);
			option.value = value;
			node.append(option);
		}
		return node;
	}

	function input(placeholder, type = "text") {
		const node = element("input");
		node.type = type;
		node.placeholder = translate(placeholder);
		return node;
	}

	function dateLabel(value) {
		const time = Date.parse((value || "").replace(" ", "T"));
		return Number.isNaN(time) ? "" : new Date(time).toLocaleString();
	}

	function messageId() {
		return Array.from(crypto.getRandomValues(new Uint8Array(16)), (value) =>
			value.toString(16).padStart(2, "0")).join("");
	}

	function safeLink(url) {
		try {
			const link = new URL(url, location.origin);
			return link.origin === location.origin ? link.href : null;
		} catch {
			return null;
		}
	}

	class Messaging {
		constructor(access, ai) {
			this.access = access;
			this.ai = ai;
			this.tabs = [...(access.team ? ["messages"] : []), "notifications",
				...(access.whatsapp ? ["whatsapp"] : [])];
			this.data = { threads: [], notifications: [], erp_unread: 0 };
			this.tab = null;
			this.thread = null;
			this.filter = "all";
			this.history = [];
			this.more = false;
			this.moreAfter = false;
			this.historyVersion = 0;
			this.view = element("section", "esafe-messaging-view");
			this.view.hidden = true;
			this.status = element("div", "esafe-messaging-status");
			this.status.setAttribute("role", "status");
			this.content = element("div", "esafe-messaging-content");
			this.view.append(this.status, this.content);
		}

		async call(name, args = {}, write = false, file = null) {
			const endpoint = server + (name.includes(".") ? name : "messaging." + name);
			const url = new URL(endpoint, location.origin);
			const init = { credentials: "same-origin", cache: "no-store", headers: {} };
			if (write) {
				init.method = "POST";
				init.headers["X-Frappe-CSRF-Token"] = this.access.csrf;
				if (file) {
					init.body = new FormData();
					for (const [key, value] of Object.entries(args)) {
						if (value != null) init.body.append(key, value);
					}
					init.body.append("file", file);
				} else {
					init.headers["Content-Type"] = "application/json";
					init.body = JSON.stringify(args);
				}
			} else {
				for (const [key, value] of Object.entries(args)) {
					if (value != null) url.searchParams.set(key, value);
				}
			}
			const response = await fetch(url, init);
			if (!response.ok) {
				const payload = await response.json().catch(() => ({}));
				let message = payload.message;
				try {
					const item = JSON.parse(payload._server_messages || "[]").at(-1);
					if (item) message = JSON.parse(item).message;
				} catch {
					// Fall back to a short message when the server returns a nonstandard error.
				}
				const error = new Error(typeof message === "string" ? message : translate("The request failed. Try again."));
				error.status = response.status;
				throw error;
			}
			return (await response.json()).message;
		}

		mount() {
			if (this.ai) {
				this.panel = this.ai.panel;
				this.tabBar = this.panel.querySelector(".ask_esafe_ai-tabs");
				this.launcher = this.ai.bubbleEl;
				this.ai.collaboration = this;
				this.panel.append(this.view);
			} else {
				const root = element("div", "esafe-messaging-root");
				this.launcher = button("Open ASK ESAFE AI", () => this.open(), "esafe-messaging-launcher");
				this.launcher.setAttribute("aria-label", translate("Open ASK ESAFE AI"));
				this.launcher.textContent = "";
				const emblem = element("img");
				emblem.src = asset + "img/esafe-ai-emblem.svg";
				emblem.alt = "";
				this.launcher.append(emblem);
				this.panel = element("section", "esafe-messaging-panel");
				this.panel.hidden = true;
				this.panel.setAttribute("aria-label", "ASK ESAFE AI");
				const header = element("header", "esafe-messaging-panel-header");
				const logo = element("img");
				logo.src = asset + "img/esafe-ai-wordmark.svg";
				logo.alt = "ASK ESAFE AI";
				header.append(logo, button("Close", () => {
					this.panel.hidden = true;
					this.launcher.hidden = false;
					this.activate(null);
					this.launcher.focus();
				}));
				this.tabBar = element("div", "esafe-messaging-tabs");
				this.panel.append(header, this.tabBar, this.view);
				root.append(this.launcher, this.panel);
				document.body.append(root);
			}

			for (const tab of this.tabs) {
				const node = button(tabs[tab], () => this.open(tab), "nav-link ask_esafe_ai-tab esafe-messaging-tab");
				node.dataset.tab = tab;
				node.setAttribute("role", "tab");
				node.setAttribute("aria-selected", "false");
				if (this.ai) {
					const item = element("li", "nav-item");
					item.append(node);
					this.tabBar.append(item);
					this.ai.tabEls.push(node);
				} else {
					this.tabBar.append(node);
				}
				if (tab === "notifications") this.notificationTab = node;
			}
			if (!this.ai) this.tabBar.setAttribute("role", "tablist");
			this.badge = element("span", "esafe-messaging-badge");
			this.badge.hidden = true;
			this.launcher.append(this.badge);

			const refresh = () => { if (!document.hidden) void this.refresh(); };
			for (const event of ["ask_esafe_ai_messaging_changed", "notification", "indicator_hide"]) {
				window.frappe?.realtime?.on?.(event, refresh);
			}
			window.frappe?.realtime?.socket?.on?.("connect", refresh);
			window.addEventListener("focus", refresh);
			document.addEventListener("visibilitychange", refresh);
			window.setInterval(refresh, 15000);
			refresh();
		}

		open(tab = this.tabs[0]) {
			if (this.ai) {
				this.ai.setActiveTab(tab);
			} else {
				this.launcher.hidden = true;
				this.panel.hidden = false;
				for (const node of this.tabBar.children) {
					node.setAttribute("aria-selected", String(node.dataset.tab === tab));
				}
				this.activate(tab);
			}
		}

		visible() {
			return this.tab && !this.panel.hidden && (!this.ai || this.ai.state.open);
		}

		async run(action) {
			this.status.textContent = "";
			try {
				return await action();
			} catch (error) {
				this.status.textContent = error.message;
			}
		}

		async refresh() {
			if (this.refreshInFlight) {
				this.refreshPending = true;
				return;
			}
			this.refreshInFlight = true;
			try {
				this.data = await this.call("overview");
				this.updateDeskBell();
				const unread = this.data.threads.filter((thread) => thread.unread).length + this.data.erp_unread;
				this.badge.hidden = unread === 0;
				this.badge.textContent = unread > 99 ? "99+" : String(unread);
				this.launcher.setAttribute(
					"aria-label", unread ? translate("Open ASK ESAFE AI") + " (" + unread + ")" : translate("Open ASK ESAFE AI"),
				);
				this.notificationTab.textContent = translate("Notifications") + (unread ? " (" + unread + ")" : "");
				if (this.visible() && this.thread && !this.data.threads.some((row) => row.name === this.thread.name)) {
					this.closeThread();
				} else if (this.visible() && !this.formOpen) {
					if (!this.thread) {
						this.renderList();
					} else {
						const current = this.data.threads.find((thread) => thread.name === this.thread.name);
						if (!current) {
							this.closeThread();
						} else {
							const previous = this.thread;
							this.thread = current;
							if (previous.assignee !== current.assignee || previous.manager !== current.manager) {
								await this.openThread(current);
							} else {
								if (previous.updated !== current.updated || current.kind === "WhatsApp") {
									await this.loadHistory({ refresh: true });
								}
								const windowOpen = Date.parse(current.reply_until) > Date.now();
								if (current.kind === "WhatsApp" && current.reply_until &&
									(windowOpen !== this.replyWindowOpen || previous.opted_in !== current.opted_in)) {
									await this.renderComposer(current);
								}
							}
						}
					}
				}
			} catch (error) {
				if (error.status === 403 || error.status === 401) {
					this.data = { threads: [], notifications: [], erp_unread: 0 };
					this.closeThread();
					this.badge.hidden = true;
				}
				if (this.visible()) this.status.textContent = error.message;
			} finally {
				this.refreshInFlight = false;
				if (this.refreshPending) {
					this.refreshPending = false;
					void this.refresh();
				}
			}
		}

		updateDeskBell() {
			if (!window.frappe?.boot) return;
			const count = this.data.erp_unread;
			window.frappe.boot.notification_unread_count = count;
			for (const badge of document.querySelectorAll(".notification-count")) {
				badge.textContent = count > 99 ? "99+" : String(count);
				badge.classList.toggle("hidden", count === 0);
				badge.setAttribute("aria-label", count + " " + translate("unread notifications"));
			}
		}

		activate(tab) {
			const previous = this.tab;
			this.tab = tab;
			this.view.hidden = !tab;
			if (!tab) return;
			this.formOpen = false;
			if (tab !== previous) this.closeThread();
			else if (!this.thread) this.renderList();
			void this.refresh();
		}

		closeThread() {
			this.thread = null;
			this.formOpen = false;
			this.historyVersion += 1;
			if (this.tab) this.renderList();
		}

		renderList() {
			this.content.replaceChildren();
			if (this.tab === "notifications") {
				this.renderNotifications();
				return;
			}
			const toolbar = element("div", "esafe-messaging-toolbar");
			toolbar.append(element("strong", "", translate(tabs[this.tab])));
			if (this.tab === "messages") {
				toolbar.append(button("New chat", () => this.run(() => this.newChat())));
			}
			const rows = this.data.threads.filter((row) => (row.kind === "WhatsApp") === (this.tab === "whatsapp"));
			const list = element("div", "esafe-messaging-scroll");
			for (const thread of rows) {
				const item = button(thread.title, () => this.run(() => this.openThread(thread)), "esafe-messaging-list-item");
				if (thread.unread) item.dataset.unread = "true";
				const description = thread.kind === "WhatsApp" ? thread.assignee || translate("Unassigned") : translate(thread.kind);
				item.append(element("small", "", description));
				list.append(item);
			}
			if (!rows.length) list.append(element("p", "esafe-messaging-empty", translate("No conversations yet.")));
			this.content.append(toolbar, list);
		}

		renderNotifications() {
			const bar = element("div", "esafe-messaging-toolbar");
			const options = [["all", "All"], ["chat", "Chat"], ["erp", "ERPNext"]];
			if (this.access.whatsapp) options.push(["whatsapp", "WhatsApp"]);
			const filter = select(options.map(([key, text]) => [key, translate(text)]));
			filter.value = this.filter;
			filter.setAttribute("aria-label", translate("Filter notifications"));
			filter.addEventListener("change", () => {
				this.filter = filter.value;
				this.renderList();
			});
			bar.append(element("strong", "", translate("Notifications")), filter);
			this.content.append(bar);

			const alerts = [
				...this.data.threads.filter((thread) => thread.unread).map((thread) => ({
					kind: thread.kind === "WhatsApp" ? "whatsapp" : "chat", title: thread.title,
					date: thread.unread_at, unread: true, thread,
				})),
				...this.data.notifications.map((row) => ({
					kind: "erp", title: row.title, date: row.creation, unread: !row.read, row,
				})),
			].filter((item) => this.filter === "all" || item.kind === this.filter);
			alerts.sort((a, b) => String(b.date).localeCompare(String(a.date)));
			const list = element("div", "esafe-messaging-scroll");
			for (const alert of alerts) {
				const item = button(alert.title, () => this.run(async () => {
					if (alert.thread) {
						this.open(alert.kind === "whatsapp" ? "whatsapp" : "messages");
						await this.openThread(alert.thread, true);
					} else {
						await this.call("read_notification", { name: alert.row.name }, true);
						const url = alert.row.url && safeLink(alert.row.url);
						if (url) location.assign(url);
						else {
							this.formOpen = true;
							const detail = element("div", "esafe-messaging-form");
							detail.append(button("Back", () => { this.closeThread(); void this.refresh(); }),
								element("strong", "", alert.title), element("p", "", alert.row.description || ""));
							this.content.replaceChildren(detail);
							await this.refresh();
						}
					}
				}), "esafe-messaging-list-item");
				item.dataset.unread = String(alert.unread);
				const type = options.find(([key]) => key === alert.kind)?.[1];
				item.append(element("small", "", [translate(type), dateLabel(alert.date)].filter(Boolean).join(" · ")));
				list.append(item);
			}
			if (!alerts.length) list.append(element("p", "esafe-messaging-empty", translate("No notifications.")));
			this.content.append(list);
		}

		async newChat() {
			const directory = await this.call("users");
			const kind = select([["0", translate("Direct message")], ["1", translate("Private group")]]);
			const members = select(directory.filter((row) => row.name !== this.access.user)
				.map((row) => [row.name, row.full_name || row.name]));
			const name = input("Group name");
			const nameField = label("Group name", name);
			nameField.hidden = true;
			kind.addEventListener("change", () => {
				nameField.hidden = kind.value !== "1";
				members.multiple = kind.value === "1";
			});
			const form = element("div", "esafe-messaging-form");
			form.append(button("Back", () => this.closeThread()), label("Conversation type", kind),
				nameField, label("People", members), button("Start chat", () => this.run(async () => {
					const thread = await this.call("start_thread", {
						members: [...members.selectedOptions].map((option) => option.value),
						title: name.value, group: Number(kind.value),
					}, true);
					this.formOpen = false;
					await this.openThread(await this.call("thread_info", { thread }));
					await this.refresh();
				})));
			this.formOpen = true;
			this.content.replaceChildren(form);
		}

		async openThread(thread, unread = false) {
			this.formOpen = false;
			this.thread = thread;
			this.historyVersion += 1;
			this.history = [];
			this.content.replaceChildren();
			const header = element("div", "esafe-messaging-toolbar");
			header.append(button("Back", () => this.closeThread()), element("strong", "", thread.title));
			if (thread.kind === "Group" || thread.kind === "WhatsApp") {
				header.append(button("Manage", () => this.run(() => this.manage())));
			}
			this.transcript = element("div", "esafe-messaging-scroll esafe-messaging-transcript");
			this.transcript.setAttribute("aria-label", translate("Conversation history"));
			this.composer = element("div", "esafe-messaging-composer");
			this.content.append(header, this.transcript, this.composer);
			await this.loadHistory({ unread });
			if (this.thread?.name === thread.name) await this.renderComposer(thread);
		}

		async loadHistory({ before, after, unread = false, refresh = false } = {}) {
			if (refresh && this.loadingHistory) return;
			const name = this.thread?.name;
			if (!name || this.formOpen) return;
			const version = ++this.historyVersion;
			if (refresh && this.history.length) before = this.history.at(-1).sequence + 1;
			this.loadingHistory = true;
			try {
				let result = await this.call("history", { thread: name, before, after, unread: Number(unread) });
				if (version !== this.historyVersion || this.thread?.name !== name) return;
				if (refresh && this.history.length && !this.moreAfter) {
					const newer = await this.call("history", { thread: name, after: this.history.at(-1).sequence });
					if (version !== this.historyVersion || this.thread?.name !== name) return;
					result = { ...result, ...newer, more: result.more, messages: [...result.messages, ...newer.messages] };
				}
				const known = new Map(this.history.map((row) => [row.name, row]));
				for (const message of result.messages) known.set(message.name, message);
				this.history = [...known.values()].sort((a, b) => a.sequence - b.sequence);
				if (after == null) this.more = Boolean(result.more);
				if (!before || refresh) this.moreAfter = Boolean(result.more_after) || (refresh && this.moreAfter);
				const priorTop = this.transcript.scrollTop;
				this.renderHistory();
				this.transcript.scrollTop = unread ? 0 : (before && !refresh ? priorTop : this.transcript.scrollHeight);
				const last = this.history.at(-1);
				if (last && this.visible() && !document.hidden && last.sequence > (this.thread.last_read || 0)) {
					await this.call("mark_read", { thread: name, sequence: last.sequence }, true);
					if (this.thread?.name === name) this.thread.last_read = last.sequence;
				}
			} finally {
				if (version === this.historyVersion) this.loadingHistory = false;
			}
		}

		renderHistory() {
			this.transcript.replaceChildren();
			if (this.more && this.history.length) this.transcript.append(button("Earlier messages", () =>
				this.run(() => this.loadHistory({ before: this.history[0].sequence }))));
			for (const row of this.history) {
				const own = row.sender === this.access.user;
				const card = element("article", "esafe-messaging-message");
				card.dataset.own = String(own);
				const author = own ? translate("You") : row.sender || this.thread.title;
				card.append(element("small", "", [author, dateLabel(row.creation), row.status && translate(row.status)]
					.filter(Boolean).join(" · ")));
				if (row.body) card.append(element("div", "esafe-messaging-text", row.body));
				if (row.attachment) {
					const link = element("a", "", row.attachment);
					link.href = server + "messaging.download?" + new URLSearchParams({ message: row.name });
					link.target = "_blank";
					link.rel = "noopener";
					card.append(link);
				} else if (row.restricted || row.attachment_pending) {
					card.append(element("div", "", translate(row.restricted ? "Attachment restricted" : "Downloading attachment…")));
				}
				this.transcript.append(card);
			}
			if (this.moreAfter) this.transcript.append(button("More recent messages", () =>
				this.run(() => this.loadHistory({ after: this.history.at(-1).sequence }))));
		}

		async renderComposer(thread) {
			const form = this.composer;
			form.replaceChildren();
			const isWhatsApp = thread.kind === "WhatsApp";
			const options = isWhatsApp ? await this.call("whatsapp.composer", { thread: thread.name }) : { open: true };
			if (form !== this.composer || thread.name !== this.thread?.name) return;
			this.replyWindowOpen = options.open;
			if (isWhatsApp && thread.assignee !== this.access.user) {
				form.append(element("p", "", translate(thread.assignee ? "Only the assigned agent can reply." : "Claim this conversation to reply.")));
				if (!thread.assignee) form.append(button("Claim conversation", () => this.run(async () => {
					await this.call("whatsapp.assign", { thread: thread.name }, true);
					await this.openThread(await this.call("thread_info", { thread: thread.name }));
					await this.refresh();
				})));
				return;
			}
			const text = element("textarea");
			text.rows = 2;
			text.maxLength = isWhatsApp ? 4096 : 8000;
			text.placeholder = translate("Write a message…");
			text.setAttribute("aria-label", translate("Message"));
			const file = input("Upload a file", "file");
			let recordFile = null;
			const attachment = element("span", "esafe-messaging-attachment");
			const template = select([["", translate("Choose an approved template")], ...(options.templates || []).map((item) => [item, item])]);
			let retryId = messageId();
			const resetId = () => { retryId = messageId(); };
			text.addEventListener("input", resetId);
			file.addEventListener("change", resetId);
			template.addEventListener("change", resetId);
			const send = button("Send", () => this.run(async () => {
				send.disabled = true;
				try {
					await this.call("send", {
						thread: thread.name, client_id: retryId,
						body: options.open ? text.value : "", record_file: recordFile,
						template: options.open ? null : template.value,
					}, true, file.files[0]);
					text.value = "";
					file.value = "";
					template.value = "";
					recordFile = null;
					attachment.textContent = "";
					resetId();
					await this.loadHistory({ refresh: true });
					await this.refresh();
				} finally {
					send.disabled = false;
				}
			}));
			if (options.open) {
				form.append(text, label("Upload a file", file));
				if (!isWhatsApp) {
					form.append(button("Link ERPNext attachment", () => this.run(() =>
						this.chooseRecord((item) => {
							recordFile = item?.id || null;
							attachment.textContent = item?.label || "";
							file.value = "";
							resetId();
						}))), attachment);
					file.addEventListener("change", () => { recordFile = null; attachment.textContent = ""; });
				}
			} else {
				form.append(element("p", "", translate("The WhatsApp reply window is closed.")), template);
				if (!options.templates?.length) send.disabled = true;
			}
			form.append(send);
		}

		async chooseRecord(chosen) {
			const type = input("Document type");
			const name = input("Record ID");
			const dialog = element("div", "esafe-messaging-form esafe-messaging-record");
			const results = element("div", "esafe-messaging-scroll");
			dialog.append(label("Document type", type), label("Record ID", name),
				button("Find attachments", () => this.run(async () => {
					const files = await this.call("record_files", { doctype: type.value, document: name.value });
					results.replaceChildren();
					for (const file of files) {
						results.append(button(file.label, () => { chosen(file); dialog.remove(); }));
					}
					if (!files.length) results.append(element("p", "", translate("No accessible attachments.")));
				})), results, button("Clear attachment", () => { chosen(null); dialog.remove(); }),
				button("Cancel", () => dialog.remove()));
			this.composer.querySelector(".esafe-messaging-record")?.remove();
			this.composer.append(dialog);
		}

		async manage() {
			const thread = this.thread;
			const whatsapp = thread.kind === "WhatsApp";
			const directory = await this.call("users", { whatsapp: Number(whatsapp) });
			if (this.thread?.name !== thread.name) return;
			const form = element("div", "esafe-messaging-form");
			form.append(button("Back", () => this.run(() => this.openThread(thread))));
			const people = select(directory.filter((row) => row.name !== this.access.user)
				.map((row) => [row.name, row.full_name || row.name]));
			const apply = async (endpoint, args) => {
				await this.call(endpoint, { thread: thread.name, ...args }, true);
				this.formOpen = false;
				if (args.action === "leave") this.closeThread();
				else await this.openThread(await this.call("thread_info", { thread: thread.name }));
				await this.refresh();
			};
			if (whatsapp) {
				form.append(element("p", "", thread.assignee || translate("Unassigned")));
				if (thread.assignee === this.access.user || !thread.assignee) {
					form.append(label("Agent", people),
						button("Assign", () => this.run(() => apply("whatsapp.assign", { agent: people.value }))));
					if (thread.assignee === this.access.user) {
						const options = await this.call("whatsapp.composer", { thread: thread.name });
						const consent = input("", "checkbox");
						consent.checked = options.opted_in;
						form.append(label("Customer has opted in to WhatsApp follow-ups", consent),
							button("Save consent", () => this.run(() =>
								apply("whatsapp.record_consent", { granted: Number(consent.checked) }))));
					}
				}
			} else {
				form.append(element("p", "", thread.members.join(", ")));
				if (thread.manager === this.access.user) {
					const title = input("Group name");
					title.value = thread.title;
					form.append(label("Group name", title), button("Rename group", () =>
						this.run(() => apply("update_group", { action: "rename", value: title.value }))));
					form.append(label("Person", people));
					for (const [action, title] of [["add", "Add member"], ["remove", "Remove member"], ["transfer", "Transfer ownership"]]) {
						form.append(button(title, () => this.run(() =>
							apply("update_group", { action, value: people.value }))));
					}
				} else {
					form.append(button("Leave group", () => this.run(() => apply("update_group", { action: "leave" }))));
				}
			}
			if (this.thread?.name !== thread.name) return;
			this.formOpen = true;
			this.content.replaceChildren(form);
		}
	}

	async function mount() {
		const response = await fetch(server + "messaging.bootstrap", { credentials: "same-origin", cache: "no-store" });
		if (!response.ok) return;
		const { message: access } = await response.json();
		if (!access?.team && !access?.whatsapp) return;
		const style = element("link");
		style.rel = "stylesheet";
		style.href = asset + "css/messaging.css";
		document.head.append(style);
		const ai = window.ask_esafe_aiWidget;
		if (ai && window.frappe?.boot?.ask_esafe_ai?.allowed) ai.init();
		new Messaging(access, ai?.panel ? ai : null).mount();
	}

	if (window.askEsafeMessagingLoading) return;
	window.askEsafeMessagingLoading = true;
	const start = () => void mount().catch((error) => console.warn("ASK ESAFE AI messaging could not load.", error));
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
	else start();
})();
