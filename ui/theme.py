"""
T.A.G.A.P. - UI Theme & Constants
"""
import flet as ft

# --- Colors from your Flet Studio design ---
PRIMARY_RED = "#BA384B"
PRIMARY_RED_LIGHT = "#D45A6B"
BG_OFF_WHITE = "#FBF9FA"
CARD_WHITE = "#FFFFFF"
INK = "#29262A"
MUTED = "#AAA4A7"
BORDER_COLOR = "#EDE8E9"
SUCCESS_GREEN = "#397E68"
WARNING_YELLOW = "#D9A05B"

# --- Admin shell colors ---
ADMIN_SIDEBAR_BG = "#FFFFFF"
ADMIN_CONTENT_BG = "#F5F1F3"       # slightly warmer than BG_OFF_WHITE
ADMIN_NAV_ACTIVE_BG = "#FBE9EC"
ADMIN_NAV_ACTIVE_TEXT = PRIMARY_RED
ADMIN_NAV_HOVER_BG = "#F5F0F2"

# --- Card-specific colors ---
COLOR_SAFE = SUCCESS_GREEN
COLOR_ASSIST = WARNING_YELLOW
COLOR_DANGER = PRIMARY_RED
COLOR_ADMIN = INK

def get_card_color(card_type: str) -> str:
    if card_type == "SAFE": return COLOR_SAFE
    if card_type == "ASSIST": return COLOR_ASSIST
    if card_type == "DANGER": return COLOR_DANGER
    return COLOR_ADMIN

def get_card_icon(card_type: str) -> str:
    if card_type == "SAFE": return ft.Icons.SHIELD_OUTLINED
    if card_type == "ASSIST": return ft.Icons.MEDICAL_SERVICES_OUTLINED
    if card_type == "DANGER": return ft.Icons.WARNING_AMBER_ROUNDED
    return ft.Icons.ADMIN_PANEL_SETTINGS