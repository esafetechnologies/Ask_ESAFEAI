const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const test = require("node:test");
const source = readFileSync("ask_esafe_ai/public/js/website_widget.js", "utf8");

function fixture({ path = "/pos", allowed = true, embedded = false, initialized = true } = {}) {
	const events = {};
	class Element {
		constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.attributes = {}; }
		append(node) { this.children.push(node); }
		setAttribute(key, value) { this.attributes[key] = value; }
		addEventListener(key, fn) { this.listeners[key] = fn; }
		focus() { this.focused = true; }
		remove() { this.removed = true; }
		querySelector(selector) { return this.controls?.[selector] || null; }
		set innerHTML(value) {
			this.controls = Object.fromEntries([".esafe-launcher", "section", ".esafe-load-status", ".esafe-website-close"]
				.map(key => [key, new Element(key)]));
		}
	}
	const doc = {
		readyState: "complete", head: new Element("head"), body: new Element("body"),
		createElement(tag) {
			const element = new Element(tag);
			if (tag === "iframe") { element.contentDocument = childDoc; element.contentWindow = child; }
			return element;
		},
	};
	const childDoc = { head: new Element("head"),
		createElement: () => Object.assign(new Element("link"), {sheet: {}}),
		getElementById: id => childDoc.head.children.find(node => node.id === id),
		querySelector: () => null,
	};
	const widget = { initialized, state: {messages: ["saved conversation"], draft: "unsent"},
		toggle(open) { this.open = open; } };
	const child = { ask_esafe_aiWidget: widget, addEventListener() {} };
	const win = { addEventListener(name, handler) { events[name] = handler; } };
	win.parent = embedded ? {} : win;
	let requests = 0;
	const timers = [];
	const context = vm.createContext({ window: win, document: doc,
		location: {pathname: path, hash: "#/register", search: "?private=ignored"}, console,
		fetch: async () => { requests++; return {ok: true, json: async () => ({message: {allowed}})}; },
		setTimeout: fn => timers.push(fn), Date,
	});
	vm.runInContext(source, context);
	return {doc, child, widget, events, context, timers, get requests() {return requests;}};
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test("same-site POS opens the full assistant and reuses history and draft on reopen", async () => {
	const f = fixture(); await flush();
	const root = f.doc.body.children[0];
	const launcher = root.querySelector(".esafe-launcher");
	launcher.listeners.click();
	const panel = root.querySelector("section");
	assert.equal(panel.children[0].src, "/desk");
	assert.equal(panel.children[0].hidden, false);
	assert.equal(f.widget.open, true);
	assert.equal(f.child.askEsafeHostContext.route, "/pos#/register");
	assert.equal(JSON.stringify(f.child.askEsafeHostContext).includes("private"), false);
	root.querySelector(".esafe-website-close").listeners.click();
	assert.equal(panel.hidden, true);
	launcher.listeners.click();
	assert.equal(panel.children.length, 1);
	assert.deepEqual(f.widget.state, {messages:["saved conversation"], draft:"unsent"});
	vm.runInContext(source, f.context); await flush();
	assert.equal(f.requests, 1);
	assert.equal(f.doc.body.children.length, 1);
	f.context.location.hash = "#/history";
	f.events.hashchange();
	assert.equal(f.child.askEsafeHostContext.route, "/pos#/history");
});

test("Desk, nested frames and unauthorized users never create a second launcher", async () => {
	for (const options of [{path:"/desk/setup/home"}, {path:"/app"}, {embedded:true}, {allowed:false}]) {
		const f = fixture(options); await flush();
		assert.equal(f.doc.body.children.length, 0);
	}
});

test("a slow Desk boot stays hidden until its assistant is ready", async () => {
	const f = fixture({initialized:false}); await flush();
	const root = f.doc.body.children[0];
	root.querySelector(".esafe-launcher").listeners.click();
	const frame = root.querySelector("section").children[0];
	assert.equal(frame.hidden, true);
	assert.equal(f.timers.length, 1);
	f.widget.initialized = true;
	f.timers.shift()();
	assert.equal(frame.hidden, false);
});
