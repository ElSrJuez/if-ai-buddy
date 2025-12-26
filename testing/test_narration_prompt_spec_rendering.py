import unittest
from pathlib import Path

from module.narration_job_builder import NarrationJobBuilder


class NarrationPromptSpecRenderingTests(unittest.TestCase):
    def test_renders_absence_as_meaningful_text(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config = {
            "_project_root": str(project_root),
            "llm_narration_system_prompt": "system",
            "llm_narration_user_prompt_template_spec_path": "config/llm_narration_user_prompt_template.json",
        }

        builder = NarrationJobBuilder(config)

        memory_context = {
            "player_name": "Tester",
            "turn_count": 1,
            "current_room": "Nowhere",
            "current_scene": {
                "room_name": "Nowhere",
                "visit_count": 1,
                "description_lines": ["A featureless test room."],
                "current_items": [],
                "npcs": [],
                "action_records": [],
                "narrations": [],
                "scene_intro_collection": [],
            },
            "player_state": {"inventory": []},
            "recent_scene_summaries": [],
        }

        job = builder.build_job(memory_context=memory_context, trigger="turn", latest_transcript=None)
        user_prompt = job.messages[1]["content"]

        self.assertIn("Turn 1. Tester is in Nowhere.", user_prompt)
        # Absence is data:
        self.assertIn("Tester is carrying nothing.", user_prompt)
        self.assertIn("Tester hasn't done anything notable in this location yet.", user_prompt)
        self.assertIn("You (Narrator) haven't narrated this location yet.", user_prompt)
        self.assertIn("Right now, nothing obvious stands out as an interactable object for Tester.", user_prompt)


if __name__ == "__main__":
    unittest.main()
