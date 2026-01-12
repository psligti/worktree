import json
import tempfile
import unittest
from pathlib import Path

from wt.config.loader import load_config


class TestConfigLoader(unittest.TestCase):
    def test_profile_merge_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            config_dir = repo_root / ".wt" / "config" / "profiles"
            config_dir.mkdir(parents=True)

            (repo_root / ".wt" / "config" / "wt.toml").write_text(
                """
                [env]
                port_keys = ["APP_PORT"]
                """.strip()
                + "\n",
                encoding="utf-8",
            )
            (config_dir / "ui.toml").write_text(
                """
                [env]
                port_keys = ["APP_PORT", "UI_PORT"]
                """.strip()
                + "\n",
                encoding="utf-8",
            )

            config = load_config(str(repo_root), "ui")
            self.assertEqual(config.env.port_keys, ["APP_PORT", "UI_PORT"])

            cache_path = repo_root / ".wt" / "cache" / "resolved_config.json"
            self.assertTrue(cache_path.exists())
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(data["env"]["port_keys"], ["APP_PORT", "UI_PORT"])


if __name__ == "__main__":
    unittest.main()
