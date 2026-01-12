import tempfile
import unittest
from pathlib import Path

from orch.models import DefaultsConfig, ProjectConfig, Story, TmuxConfig
from orch.orchestrator import Orchestrator, _render_template, slugify
from orch.task_store import TaskStore
from orch.worktree_service import _parse_worktree_porcelain


class TestOrchCore(unittest.TestCase):
    def test_task_store_loads_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tasks.yaml"
            path.write_text(
                """
                version: 1
                project:
                  name: "Demo"
                  repo_root: "."
                epics:
                  - id: "E1"
                    title: "Epic"
                    stories:
                      - id: "E1-S1"
                        title: "Story"
                        acceptance_criteria:
                          - "A"
                """.strip()
                + "\n",
                encoding="utf-8",
            )
            doc = TaskStore(path).load()
            self.assertEqual(doc.epics[0].stories[0].id, "E1-S1")

    def test_slugify_and_naming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "repo"
            repo_root.mkdir()
            orch = Orchestrator(repo_root, repo_root / "tasks.yaml", repo_root / ".orch" / "state.json")
            story = Story(id="E1-S1", title="Incremental Drive Ingestion", acceptance_criteria=[])
            config = ProjectConfig(
                repo_root=repo_root,
                branch_prefix="task",
                worktree_dir_template="../{repo}-{story_id}",
                tmux=TmuxConfig(),
                defaults=DefaultsConfig(),
                providers={},
            )
            self.assertEqual(slugify(story.title), "incremental-drive-ingestion")
            self.assertEqual(orch._branch_name(config, story), "task/E1-S1-incremental-drive-ingestion")
            path = orch._worktree_path(config, story)
            self.assertTrue(path.name.endswith("repo-E1-S1"))

    def test_prompt_template_render(self) -> None:
        template = "TASK: {story_id} - {title}\n{acceptance_criteria}\n{constraints}\n"
        rendered = _render_template(
            template,
            {
                "story_id": "E1-S1",
                "title": "Demo",
                "acceptance_criteria": "- A",
                "constraints": "- C",
            },
        )
        self.assertIn("TASK: E1-S1 - Demo", rendered)

    def test_parse_worktree_porcelain(self) -> None:
        output = """
        worktree /tmp/repo
        HEAD 1234
        branch refs/heads/main
        worktree /tmp/repo-feature
        HEAD 5678
        branch refs/heads/feat
        """.strip()
        entries = _parse_worktree_porcelain(output)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].branch, "main")
        self.assertEqual(entries[1].branch, "feat")


if __name__ == "__main__":
    unittest.main()
