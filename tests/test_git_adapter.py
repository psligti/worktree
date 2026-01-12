import unittest

from wt.git import adapter


class TestGitAdapter(unittest.TestCase):
    def test_parse_worktree_porcelain(self) -> None:
        data = (
            b"worktree /repo/.worktrees/feat-x\x00"
            b"HEAD abcdef123456\x00"
            b"branch refs/heads/wt/feat-x\x00"
        )

        records = adapter._parse_worktree_porcelain_z(data)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].path, "/repo/.worktrees/feat-x")
        self.assertEqual(records[0].head_sha, "abcdef123456")
        self.assertEqual(records[0].branch, "refs/heads/wt/feat-x")


if __name__ == "__main__":
    unittest.main()
