app_name = "ask_esafe_ai"
app_title = "ASK ESAFE AI"
app_publisher = "ESAFE Technologies"
app_description = "Helps you understand ERPNext"
app_url = "https://github.com/esafetechnologies/Ask_ESAFEAI"
app_license = "agpl-3.0"
app_include_js = ["ask_esafe_ai.bundle.js", "/assets/ask_esafe_ai/js/messaging.js"]
app_include_css = "ask_esafe_ai.bundle.css"
web_include_js = "/assets/ask_esafe_ai/js/website_widget.js"
after_request = "ask_esafe_ai.ask_esafe_ai.website_widget.inject_widget"
extend_bootinfo = "ask_esafe_ai.ask_esafe_ai.boot.boot_session"
after_install = "ask_esafe_ai.ask_esafe_ai.purchase_order_scan.install_skill"
after_migrate = "ask_esafe_ai.ask_esafe_ai.purchase_order_scan.install_skill"

scheduler_events = {
	"cron": {"*/5 * * * *": ["ask_esafe_ai.ask_esafe_ai.whatsapp.recover_queued_messages"]},
}

fixtures = [
	{
		"dt": "Role",
		"filters": [["name", "in", ["ASK ESAFE AI Messaging User", "ASK ESAFE AI WhatsApp Agent"]]],
	},
]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# Includes in <head>
# ------------------

# include js, css files in header of web template
# web_include_css = "/assets/ask_esafe_ai/css/ask_esafe_ai.css"
# web_include_js = "/assets/ask_esafe_ai/js/ask_esafe_ai.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ask_esafe_ai/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "ask_esafe_ai/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "ask_esafe_ai.utils.jinja_methods",
# 	"filters": "ask_esafe_ai.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "ask_esafe_ai.install.before_install"

# Uninstallation
# ------------

# before_uninstall = "ask_esafe_ai.uninstall.before_uninstall"
# after_uninstall = "ask_esafe_ai.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ask_esafe_ai.utils.before_app_install"
# after_app_install = "ask_esafe_ai.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ask_esafe_ai.utils.before_app_uninstall"
# after_app_uninstall = "ask_esafe_ai.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ask_esafe_ai.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {}

has_permission = {}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"ask_esafe_ai.tasks.all"
# 	],
# 	"daily": [
# 		"ask_esafe_ai.tasks.daily"
# 	],
# 	"hourly": [
# 		"ask_esafe_ai.tasks.hourly"
# 	],
# 	"weekly": [
# 		"ask_esafe_ai.tasks.weekly"
# 	],
# 	"monthly": [
# 		"ask_esafe_ai.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "ask_esafe_ai.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "ask_esafe_ai.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ask_esafe_ai.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "ask_esafe_ai.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["ask_esafe_ai.utils.before_request"]
# after_request = ["ask_esafe_ai.utils.after_request"]

# Job Events
# ----------
# before_job = ["ask_esafe_ai.utils.before_job"]
# after_job = ["ask_esafe_ai.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"ask_esafe_ai.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

# Require all whitelisted methods to have type annotations
require_type_annotated_api_methods = True

default_log_clearing_doctypes = {
	"ASK ESAFE AI Conversation": 90  # days to retain logs
}

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
ignore_translatable_strings_from = ["frappe"]
