import frappe

from ask_esafe_ai.ask_esafe_ai.api import get_ask_esafe_ai_boot_payload


def boot_session(bootinfo):
	bootinfo.ask_esafe_ai = get_ask_esafe_ai_boot_payload()
