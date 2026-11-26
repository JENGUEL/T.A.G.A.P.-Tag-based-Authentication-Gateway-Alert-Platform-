import asyncio

import pytest

from ui.router import AppRouter


class FakePage:
    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog_closed = True


@pytest.mark.parametrize(
    ("action_index", "expected"),
    [(0, False), (1, True)],
)
def test_degraded_hardware_dialog_returns_operator_choice(action_index, expected):
    async def run():
        router = object.__new__(AppRouter)
        router.page = FakePage()
        decision = asyncio.create_task(
            router._confirm_degraded_hardware_mode(["GSM modem: unavailable"])
        )
        await asyncio.sleep(0)

        dialog = router.page.dialog
        dialog.actions[action_index].on_click(None)

        assert await decision is expected
        assert router.page.dialog_closed
        assert dialog.content.content.controls[1].content.value.endswith(
            "GSM modem: unavailable"
        )

    asyncio.run(run())
