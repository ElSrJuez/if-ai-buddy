import unittest

from module.game_engine_heuristics import EngineFacts, PlayerStateSnapshot
from module.game_memory import GameMemoryStore


class MemoryDescriptionSeparationTests(unittest.TestCase):
    def test_action_feedback_not_added_to_scene_description(self) -> None:
        # Use a temp-ish DB path under res/db; tests here are lightweight and the project
        # does not currently run unittest discovery by default.
        store = GameMemoryStore("TestPlayer", "res/db/TestPlayer_memory_test.json")
        store.reset()

        intro = EngineFacts(
            room_name="West of House",
            player_state=PlayerStateSnapshot(inventory=[], score=0, moves=0),
            visible_items=["a small mailbox"],
            description="West of House\nYou are standing in an open field.",
            gameException=False,
            exceptionMessage=None,
        )
        store.update_from_engine_facts(intro, command="look", previous_room=None, transcript=None)

        # Action feedback in same room should NOT be appended to description_lines.
        feedback = EngineFacts(
            room_name="West of House",
            player_state=PlayerStateSnapshot(inventory=[], score=0, moves=1),
            visible_items=["a small mailbox"],
            description="The small mailbox is closed.",
            gameException=False,
            exceptionMessage=None,
        )
        store.update_from_engine_facts(feedback, command="open mailbox", previous_room="West of House", transcript=None)

        ctx = store.get_context_for_prompt()
        desc_lines = ctx["current_scene"]["description_lines"]
        self.assertTrue(any("You are standing" in line for line in desc_lines))
        self.assertFalse(any("mailbox is closed" in line for line in desc_lines))

        store.close()


if __name__ == "__main__":
    unittest.main()
