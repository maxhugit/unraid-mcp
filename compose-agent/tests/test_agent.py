import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).parents[1] / "agent.py"
SPEC = importlib.util.spec_from_file_location("compose_agent", MODULE_PATH)
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class ComposeAgentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        (directory / "docker-compose.yml").write_text(
            "services:\n  app:\n    image: ${CODEX_APP_IMAGE}\n", encoding="utf-8"
        )
        (directory / "images.env").write_text(
            "CODEX_APP_IMAGE=ghcr.io/maxhugit/codex-webui-unraid:sha-aaaaaaa\n",
            encoding="utf-8",
        )
        self.stacks = {
            "codex-web": {
                "directory": str(directory),
                "compose_file": "docker-compose.yml",
                "env_file": "images.env",
                "image_variable": "CODEX_APP_IMAGE",
                "image_repository": "ghcr.io/maxhugit/codex-webui-unraid",
                "project_name": "codex-web",
            }
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_rejects_unlisted_stack(self):
        with self.assertRaisesRegex(agent.AgentError, "not allowlisted"):
            agent.safe_stack("other", self.stacks)

    def test_rejects_latest_tag(self):
        stack = agent.safe_stack("codex-web", self.stacks)
        with self.assertRaisesRegex(agent.AgentError, "immutable"):
            agent.validate_image(
                stack, "ghcr.io/maxhugit/codex-webui-unraid:latest"
            )

    def test_updates_allowlisted_image_and_runs_compose(self):
        image = "ghcr.io/maxhugit/codex-webui-unraid:sha-b481c72"
        with patch.object(agent, "run_command", side_effect=["pulled", "started", "healthy"]) as run:
            result = agent.update_stack("codex-web", image, self.stacks)
        self.assertTrue(result["changed"])
        self.assertEqual(result["previousImage"], "ghcr.io/maxhugit/codex-webui-unraid:sha-aaaaaaa")
        self.assertIn(image, (Path(self.temporary.name) / "images.env").read_text())
        self.assertEqual(run.call_count, 3)

    def test_restores_env_when_compose_fails(self):
        image = "ghcr.io/maxhugit/codex-webui-unraid:sha-b481c72"
        with patch.object(
            agent,
            "run_command",
            side_effect=[agent.AgentError("pull failed"), "rollback ok"],
        ):
            with self.assertRaisesRegex(agent.AgentError, "Previous image restored"):
                agent.update_stack("codex-web", image, self.stacks)
        env = (Path(self.temporary.name) / "images.env").read_text()
        self.assertIn("sha-aaaaaaa", env)


if __name__ == "__main__":
    unittest.main()
