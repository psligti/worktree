from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wt.bootstrap.templates import apply_templates
from wt.config.models import OpenCodeConfig, OpenCodeThemesConfig, WtConfig


class TestOpenCodeTemplates(unittest.TestCase):
    def test_cycles_themes_by_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            template_dir = repo_root / ".wt" / "templates" / "opencode"
            template_dir.mkdir(parents=True)
            (template_dir / "codex.json").write_text(
                json.dumps({"fontSize": 14, "theme": "base"}),
                encoding="utf-8",
            )
            (template_dir / "copilot.json").write_text(
                json.dumps({"fontSize": 12, "theme": "base"}),
                encoding="utf-8",
            )

            worktree_one = repo_root / "wt-one"
            worktree_two = repo_root / "wt-two"
            worktree_three = repo_root / "wt-three"
            worktree_one.mkdir()
            worktree_two.mkdir()
            worktree_three.mkdir()

            config = WtConfig(
                opencode=OpenCodeConfig(
                    connection="codex",
                    themes=OpenCodeThemesConfig(
                        codex=["c1", "c2"], copilot=["p1", "p2"]
                    ),
                )
            )
            apply_templates(str(repo_root), str(worktree_one), config)
            apply_templates(str(repo_root), str(worktree_two), config)

            first = json.loads(
                (worktree_one / ".opencode" / "config.json").read_text(encoding="utf-8")
            )
            second = json.loads(
                (worktree_two / ".opencode" / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(first["theme"], "c1")
            self.assertEqual(second["theme"], "c2")
            self.assertEqual(first["fontSize"], 14)

            copilot_config = WtConfig(
                opencode=OpenCodeConfig(
                    connection="copilot",
                    themes=OpenCodeThemesConfig(
                        codex=["c1", "c2"], copilot=["p1", "p2"]
                    ),
                )
            )
            apply_templates(str(repo_root), str(worktree_three), copilot_config)
            third = json.loads(
                (worktree_three / ".opencode" / "config.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(third["theme"], "p1")
            self.assertEqual(third["fontSize"], 12)


if __name__ == "__main__":
    unittest.main()
