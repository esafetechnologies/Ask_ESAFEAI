const translate = (text) => window.__?.(text) ?? text;

function node(tag, className, text = "") {
	const result = document.createElement(tag);
	result.className = className;
	result.textContent = translate(text);
	return result;
}

function icon(paths) {
	const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
	svg.setAttribute("viewBox", "0 0 24 24");
	svg.setAttribute("fill", "none");
	svg.setAttribute("stroke", "currentColor");
	svg.setAttribute("stroke-width", "1.6");
	svg.setAttribute("stroke-linecap", "round");
	svg.setAttribute("stroke-linejoin", "round");
	svg.setAttribute("aria-hidden", "true");
	for (const shape of paths) {
		const path = document.createElementNS(svg.namespaceURI, "path");
		path.setAttribute("d", shape);
		svg.append(path);
	}
	return svg;
}

export class PurchaseOrderScan {
	constructor(widget) {
		this.widget = widget;
		this.context = { ready: false };
		this.busy = false;
		this.file = null;
		this.skills = [];
		this.activeSkill = null;
		this.view = node("section", "ask_esafe_ai-skill-view");
		this.view.hidden = true;
		this.catalog = node("div", "ask_esafe_ai-skills-catalog");
		this.detail = node("div", "ask_esafe_ai-skill-detail");
		this.detail.hidden = true;
		this.view.append(this.catalog, this.detail);
		this.purchaseOrderView = node("div", "ask_esafe_ai-purchase-order-view");
		this.purchaseOrderView.append(
			node("h2", "", "Create a Purchase Order"),
			node("p", "ask_esafe_ai-skill-intro",
				"Upload a supplier quotation or scanned order. Review the extracted details before creating a draft."),
		);
		const upload = node("div", "ask_esafe_ai-scan-upload");
		upload.append(icon(["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z", "M14 2v6h6", "M8 12h8M8 16h5"]));
		this.fileName = node("strong", "", "Upload a PDF or image");
		this.choose = node("button", "ask_esafe_ai-scan-choose", "Choose document");
		this.choose.type = "button";
		this.choose.addEventListener("click", () => this.chooseDocument());
		upload.append(this.fileName, this.choose, node("small", "", "PDF, JPG or PNG"));
		this.purchaseOrderView.append(upload);
		const steps = node("ol", "ask_esafe_ai-scan-steps");
		for (const [title, description, paths] of [
			["Scan document", "Upload a supplier quotation or scanned order.",
				["M4 7h3l2-3h6l2 3h3v13H4Z", "M15 13a3 3 0 1 1-6 0 3 3 0 0 1 6 0"]],
			["Review details", "Check the extracted supplier, items, quantities and rates.",
				["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z", "M14 2v6h6M8 12h8M8 16h5"]],
			["Confirm draft", "Create a draft Purchase Order in ERPNext.",
				["M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0", "m7 12 3 3 7-7"]],
		]) {
			const step = node("li", "");
			const copy = node("div", "");
			copy.append(node("strong", "", title), node("p", "", description));
			step.append(icon(paths), copy);
			steps.append(step);
		}
		this.purchaseOrderView.append(steps);
		this.status = node("p", "ask_esafe_ai-scan-status");
		this.status.setAttribute("role", "status");
		this.action = node("button", "ask_esafe_ai-scan-action", "Scan and review");
		this.action.type = "button";
		this.action.addEventListener("click", () => this.startScan());
		this.manage = node("button", "ask_esafe_ai-scan-manage", "Manage skill");
		this.manage.type = "button";
		this.manage.hidden = true;
		this.manage.addEventListener("click", () =>
			frappe.set_route("Form", "ASK ESAFE AI Skill", this.context.skill));
		this.purchaseOrderView.append(this.status, this.action, this.manage);
		widget.panel.append(this.view);
		const item = node("li", "nav-item");
		const tab = node("button", "nav-link ask_esafe_ai-tab", "Skills");
		tab.type = "button";
		tab.dataset.tab = "skills";
		tab.setAttribute("role", "tab");
		tab.setAttribute("aria-selected", "false");
		tab.addEventListener("click", () => widget.setActiveTab("skills"));
		item.append(tab);
		widget.panel.querySelector(".ask_esafe_ai-tabs").append(item);
		widget.tabEls.push(tab);
		this.renderSkillList();
		this.update();
	}

	setVisible(visible) {
		this.view.hidden = !visible;
		if (visible) void this.refresh();
	}

	async refresh() {
		if (this.refreshing) return;
		this.refreshing = true;
		try {
			const response = await frappe.call({
				method: "ask_esafe_ai.ask_esafe_ai.purchase_order_scan.list_available_skills",
				type: "GET",
			});
			this.skills = response.message || [];
			this.renderSkillList();
		} catch (error) {
			this.skills = [];
			this.renderSkillList(error.message || translate("Could not load skills. Try again."));
		} finally {
			this.refreshing = false;
		}
		if (this.activeSkill === "purchase-orders-from-scans") await this.refreshPurchaseOrderContext();
	}

	renderSkillList(error = "") {
		this.catalog.replaceChildren(
			node("h2", "", "Skills"),
			node("p", "ask_esafe_ai-skill-intro", "Choose a skill to get help with an ERPNext task."),
		);
		if (error) this.catalog.append(node("p", "ask_esafe_ai-skill-error", error));
		const list = node("div", "ask_esafe_ai-skill-list");
		const purchaseSkill = this.skills.find((skill) => skill.name === "purchase-orders-from-scans");
		list.append(this.skillCard(
			purchaseSkill || {
				name: "purchase-orders-from-scans",
				title: "Create Purchase Orders from scans",
				description: "Scan a supplier quotation or order and prepare a Purchase Order draft for review.",
			},
		));
		const additionalSkills = this.skills.filter((item) => item.name !== "purchase-orders-from-scans");
		for (const skill of additionalSkills) {
			list.append(this.skillCard(skill));
		}
		if (!additionalSkills.length && !error) {
			list.append(node("p", "ask_esafe_ai-skills-empty", "More skills will appear here when they are enabled for your role."));
		}
		this.catalog.append(list);
	}

	skillCard(skill) {
		const card = document.createElement("button");
		card.type = "button";
		card.className = "ask_esafe_ai-skill-card";
		card.addEventListener("click", () => this.openSkill(skill));
		card.append(node("strong", "", skill.title || skill.name));
		const summary = (skill.description || "").replace(/[#*_`>\[\]]/g, " ").replace(/\s+/g, " ").trim();
		card.append(node("small", "", summary || "Open this skill to see what it can do."));
		return card;
	}

	openSkill(skill) {
		this.activeSkill = skill.name;
		this.catalog.hidden = true;
		this.detail.hidden = false;
		this.detail.replaceChildren();
		this.detail.append(node("button", "ask_esafe_ai-skill-back", "← All skills"));
		this.detail.querySelector(".ask_esafe_ai-skill-back").addEventListener("click", () => this.showCatalog());
		if (skill.name === "purchase-orders-from-scans") {
			this.detail.append(this.purchaseOrderView);
			void this.refreshPurchaseOrderContext();
			return;
		}
		this.detail.append(node("h2", "", skill.title || skill.name));
		const description = node("div", "ask_esafe_ai-skill-description");
		if (skill.description && typeof frappe.markdown === "function") {
			description.innerHTML = frappe.markdown(skill.description);
		} else {
			description.textContent = skill.description || "No instructions have been added to this skill yet.";
		}
		this.detail.append(description);
		const use = node("button", "ask_esafe_ai-skill-use", "Use this skill in Chat");
		use.type = "button";
		use.addEventListener("click", () => this.useSkillInChat(skill));
		this.detail.append(use);
	}

	showCatalog() {
		this.activeSkill = null;
		this.detail.hidden = true;
		this.catalog.hidden = false;
		this.update();
	}

	useSkillInChat(skill) {
		const prompt = `Use the ASK ESAFE AI skill named “${skill.name}” (${skill.title || skill.name}) to help me.`;
		this.widget.setActiveTab("chat");
		this.widget.inputEl.value = [this.widget.inputEl.value.trim(), prompt].filter(Boolean).join("\n");
		this.widget.autoResizeInput();
		this.widget.inputEl.focus();
	}

	async refreshPurchaseOrderContext() {
		try {
			const response = await frappe.call({
				method: "ask_esafe_ai.ask_esafe_ai.purchase_order_scan.get_context",
				type: "GET",
			});
			this.context = response.message;
			this.status.textContent = this.context.reason || "";
			this.manage.hidden = !this.context.can_manage;
		} catch (error) {
			this.context = { ready: false };
			this.status.textContent = error.message || translate("Could not load Purchase Order scanning. Try again.");
		}
		this.update();
	}

	update() {
		if (this.file && this.conversation !== this.widget.state.conversation?.name) {
			this.file = null;
			this.fileName.textContent = translate("Upload a PDF or image");
			this.choose.textContent = translate("Choose document");
		}
		const blocked = this.busy || this.widget.state.loading || !this.context.ready;
		this.choose.disabled = Boolean(blocked);
		this.action.disabled = Boolean(blocked || !this.file);
		this.action.textContent = translate(this.busy ? "Preparing document…" : "Scan and review");
	}

	chooseDocument() {
		if (this.choose.disabled) return;
		const conversation = this.widget.state.conversation?.name;
		if (!conversation) {
			this.status.textContent = translate("The chat is still loading. Try again in a moment.");
			return;
		}
		new frappe.ui.FileUploader({
			doctype: "ASK ESAFE AI Conversation",
			docname: conversation,
			make_attachments_public: false,
			restrictions: { allowed_file_types: [".pdf", ".jpg", ".jpeg", ".png"] },
			on_success: async (file) => {
				this.busy = true;
				this.update();
				try {
					if (!await this.widget.onFileUploaded(file, conversation)) {
						throw new Error(translate("Could not attach the document. Try again."));
					}
					if (this.widget.state.conversation?.name !== conversation) return;
					this.file = file;
					this.conversation = conversation;
					this.fileName.textContent = file.file_name;
					this.choose.textContent = translate("Choose another document");
					this.status.textContent = translate("Ready to extract and review in Chat.");
				} catch (error) {
					this.status.textContent = error.message || translate("Could not attach the document. Try again.");
				} finally {
					this.busy = false;
					this.update();
				}
			},
		});
	}

	async startScan() {
		if (this.action.disabled) return;
		this.busy = true;
		this.update();
		try {
			const response = await frappe.call({
				method: "ask_esafe_ai.ask_esafe_ai.purchase_order_scan.prepare_scan",
				type: "POST",
				args: { file_id: this.file.name, conversation: this.conversation },
			});
			if (this.widget.state.conversation?.name !== this.conversation) {
				this.status.textContent = translate("Choose a document for the current chat.");
				return;
			}
			this.widget.state.mode = "Agent";
			frappe.boot.ask_esafe_ai.agent_mode_enabled = true;
			this.widget.syncModeControl();
			this.widget.inputEl.value = response.message.message;
			await this.widget.sendMessage();
		} catch (error) {
			this.status.textContent = error.message || translate("Could not start the scan. Try again.");
		} finally {
			this.busy = false;
			this.update();
		}
	}
}
