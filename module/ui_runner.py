from __future__ import annotations

import asyncio

from module.game_controller import GameController, TurnResult
from module.ui_helper import IFBuddyTUI, EngineStatus, AIStatus


def run_ui(controller: GameController) -> None:
    """Blocking entry point to launch the new Textual UI."""

    async def _run() -> None:
        try:
            intro = await controller.bootstrap()
        except Exception as exc:  # pragma: no cover - bootstrap failures
            print(f"Failed to start session: {exc}")
            return

        app = IFBuddyTUI()

        def _after_mount() -> None:
            app.set_player_name(controller.player_name)
            app.set_engine_status(EngineStatus.READY)
            app.set_ai_status(AIStatus.IDLE)
            if intro:
                app.add_output(intro)

        app.call_after_refresh(_after_mount)

        def _handle_command(command: str) -> None:
            asyncio.create_task(_play_turn(app, controller, command))

        app.register_command_callback(_handle_command)

        try:
            await app.run_async()
        finally:
            await controller.shutdown()

    asyncio.run(_run())


async def _play_turn(app: IFBuddyTUI, controller: GameController, command: str) -> None:
    app.set_engine_status(EngineStatus.BUSY)
    app.set_ai_status(AIStatus.WORKING)

    try:
        result = await controller.play_turn(command)
    except Exception as exc:  # pragma: no cover - defensive
        app.add_error(f"Engine failure: {exc}")
        app.set_engine_status(EngineStatus.ERROR)
        app.set_ai_status(AIStatus.ERROR)
        return

    await _render_result(app, result)


async def _render_result(app: IFBuddyTUI, result: TurnResult) -> None:
    if result.error:
        app.add_error(result.error)
        app.set_engine_status(EngineStatus.ERROR)
        app.set_ai_status(AIStatus.ERROR)
        return

    if result.transcript:
        app.add_output(result.transcript)
    app.set_engine_status(EngineStatus.READY)

    if result.narration:
        app.add_narration(result.narration)
        app.set_ai_status(AIStatus.READY)
    else:
        app.set_ai_status(AIStatus.IDLE)

    if result.should_exit:
        app.exit()
