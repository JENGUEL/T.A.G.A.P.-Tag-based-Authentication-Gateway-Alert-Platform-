"""
T.A.G.A.P. - Toast Notifications
"""
import flet as ft
from ui.theme import SUCCESS_GREEN, WARNING_YELLOW, PRIMARY_RED, CARD_WHITE, INK


class Toast:
    @staticmethod
    def show(page: ft.Page, message: str, type: str = "info"):
        color = INK
        icon = ft.Icons.INFO_OUTLINE

        if type == "success":
            color = SUCCESS_GREEN
            icon = ft.Icons.CHECK_CIRCLE_OUTLINE
        elif type == "warning":
            color = WARNING_YELLOW
            icon = ft.Icons.WARNING_AMBER_ROUNDED
        elif type == "error":
            color = PRIMARY_RED
            icon = ft.Icons.ERROR_OUTLINE

        snack = ft.SnackBar(
            content=ft.Row(
                controls=[
                    ft.Icon(icon, color=color, size=20),
                    ft.Text(message, color=INK, weight=ft.FontWeight.W_500),
                ],
                spacing=10,
            ),
            bgcolor=CARD_WHITE,
            shape=ft.RoundedRectangleBorder(radius=10),
            duration=4000,
            behavior=ft.SnackBarBehavior.FLOATING,
            margin=20,
        )

        page.overlay.append(snack)
        snack.open = True
        page.update()