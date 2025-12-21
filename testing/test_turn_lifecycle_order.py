import asyncio
import unittest

from module.game_controller import GameController


class _Outcome:
    def __init__(self, transcript: str, *, moves: int | None, score: int | None, room_name: str | None) -> None:
        self.transcript = transcript
        self.moves = moves
        self.score = score
        self.room_name = room_name


class _GameApiStub:
    def __init__(self, outcome: _Outcome) -> None:
        self._outcome = outcome

    async def send(self, command: str) -> _Outcome:
        return self._outcome


class _AppStub:
    def add_transcript_output(self, text: str) -> None:
        return

    def add_narration(self, text: str) -> None:
        return


class _MemorySpy:
    def __init__(self) -> None:
        self.updated = False

    def update_from_engine_facts(self, facts, *, command=None, previous_room=None) -> None:
        self.updated = True

    def get_context_for_prompt(self) -> dict:
        return {"turn_count": 1}

    def append_narration(self, room_name: str | None, narration: str | None) -> None:
        return


class _CompletionsSpy:
    def __init__(self, memory: _MemorySpy) -> None:
        self._memory = memory

    def run(self, transcript: str, context: dict | None = None) -> dict:
        # Contract: memory update must have happened before completions are invoked.
        if not self._memory.updated:
            raise AssertionError("Memory was not updated before completions.run")
        return {"payload": {"narration": "ok"}}


class TurnLifecycleOrderingTests(unittest.TestCase):
    def test_memory_updates_before_completions(self) -> None:
        # Build a minimal controller instance without running Textual wiring.
        controller = GameController.__new__(GameController)

        # Minimal required attributes for _async_play_turn
        controller._game_api = _GameApiStub(
            _Outcome(
                transcript=(
                    "West of House                                    Score: 0        Moves: 1\n\n"
                    "You are standing in an open field west of a white house."\
                    "\n"
                ),
                moves=1,
                score=0,
                room_name="West of House",
            )
        )
        controller._app = _AppStub()
        controller._moves = 0
        controller._score = 0
        controller._room = "Unknown"

        memory = _MemorySpy()
        controller._memory = memory
        controller._completions = _CompletionsSpy(memory)

        # Status helpers are called during the flow; stub them out.
        controller._update_status = lambda **kwargs: None
        controller._set_ai_status = lambda status: None
        controller._set_engine_status = lambda status: None

        asyncio.run(controller._async_play_turn("look"))


if __name__ == "__main__":
    unittest.main()
