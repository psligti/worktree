from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from wt.domain.models import PullRequestRecord, WorktreeRecord
from wt.github.adapter import GitHubAdapter, GitHubError, PullRequest
from wt.persistence import repos
from wt.persistence.db import connect, init_db


def _create_worktree(repo_root: str, worktree_id: str) -> None:
    now = datetime.now(timezone.utc)
    record = WorktreeRecord(
        id=worktree_id,
        name=f"test-{worktree_id}",
        path=Path(repo_root) / worktree_id,
        branch=f"wt/{worktree_id}",
        lifecycle="READY",
        bootstrap="UNBOOTSTRAPPED",
        agent="DETACHED",
        runtime="STOPPED",
        created_at=now,
        updated_at=now,
    )
    with connect(repo_root) as conn:
        repos.upsert_worktree(conn, record)


class TestGitHubAdapterParsePr(unittest.TestCase):
    def test_parses_open_pr(self) -> None:
        adapter = GitHubAdapter("/tmp")
        data = {
            "number": 42,
            "title": "Test PR",
            "state": "OPEN",
            "url": "https://github.com/org/repo/pull/42",
            "headRefName": "wt/feature",
            "baseRefName": "main",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "body": "PR body",
        }
        pr = adapter._parse_pr(data)
        self.assertEqual(pr.number, 42)
        self.assertEqual(pr.title, "Test PR")
        self.assertEqual(pr.state, "open")
        self.assertEqual(pr.head_branch, "wt/feature")
        self.assertEqual(pr.base_branch, "main")
        self.assertFalse(pr.draft)
        self.assertTrue(pr.mergeable)

    def test_parses_merged_pr(self) -> None:
        adapter = GitHubAdapter("/tmp")
        data = {
            "number": 43,
            "title": "Merged PR",
            "state": "MERGED",
            "url": "https://github.com/org/repo/pull/43",
            "headRefName": "wt/merged",
            "baseRefName": "main",
            "isDraft": False,
        }
        pr = adapter._parse_pr(data)
        self.assertEqual(pr.state, "merged")

    def test_parses_closed_pr(self) -> None:
        adapter = GitHubAdapter("/tmp")
        data = {
            "number": 44,
            "title": "Closed PR",
            "state": "CLOSED",
            "url": "https://github.com/org/repo/pull/44",
            "headRefName": "wt/closed",
            "baseRefName": "main",
        }
        pr = adapter._parse_pr(data)
        self.assertEqual(pr.state, "closed")

    def test_parses_conflicting_pr(self) -> None:
        adapter = GitHubAdapter("/tmp")
        data = {
            "number": 45,
            "title": "Conflicting PR",
            "state": "OPEN",
            "url": "https://github.com/org/repo/pull/45",
            "headRefName": "wt/conflict",
            "baseRefName": "main",
            "mergeable": "CONFLICTING",
        }
        pr = adapter._parse_pr(data)
        self.assertFalse(pr.mergeable)

    def test_parses_unknown_mergeable(self) -> None:
        adapter = GitHubAdapter("/tmp")
        data = {
            "number": 46,
            "title": "Unknown Mergeable PR",
            "state": "OPEN",
            "url": "https://github.com/org/repo/pull/46",
            "headRefName": "wt/unknown",
            "baseRefName": "main",
            "mergeable": "UNKNOWN",
        }
        pr = adapter._parse_pr(data)
        self.assertIsNone(pr.mergeable)


class TestGitHubAdapterExtractPrNumber(unittest.TestCase):
    def test_extracts_number_from_url(self) -> None:
        adapter = GitHubAdapter("/tmp")
        url = "https://github.com/org/repo/pull/123"
        self.assertEqual(adapter._extract_pr_number(url), 123)

    def test_extracts_number_with_trailing_slash(self) -> None:
        adapter = GitHubAdapter("/tmp")
        url = "https://github.com/org/repo/pull/456/"
        self.assertEqual(adapter._extract_pr_number(url), 456)

    def test_raises_on_invalid_url(self) -> None:
        adapter = GitHubAdapter("/tmp")
        url = "https://github.com/org/repo/pull/not-a-number"
        with self.assertRaises(GitHubError):
            adapter._extract_pr_number(url)


class TestPullRequestRecordPersistence(unittest.TestCase):
    def test_upsert_and_get_pull_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            _create_worktree(tmpdir, "wt-123")
            record = PullRequestRecord(
                id="pr-1",
                worktree_id="wt-123",
                number=42,
                title="Test PR",
                state="open",
                url="https://github.com/org/repo/pull/42",
                head_branch="wt/feature",
                base_branch="main",
            )
            repos.upsert_pull_request(tmpdir, record)
            fetched = repos.get_pull_request(tmpdir, "wt-123", 42)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.number, 42)
            self.assertEqual(fetched.title, "Test PR")

    def test_get_pull_request_for_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            _create_worktree(tmpdir, "wt-456")
            record = PullRequestRecord(
                id="pr-2",
                worktree_id="wt-456",
                number=100,
                title="Latest PR",
                state="open",
                url="https://github.com/org/repo/pull/100",
                head_branch="wt/latest",
                base_branch="main",
            )
            repos.upsert_pull_request(tmpdir, record)
            fetched = repos.get_pull_request_for_worktree(tmpdir, "wt-456")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.number, 100)

    def test_list_pull_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            _create_worktree(tmpdir, "wt-list")
            for i in range(3):
                record = PullRequestRecord(
                    id=f"pr-{i}",
                    worktree_id="wt-list",
                    number=i + 1,
                    title=f"PR {i + 1}",
                    state="open",
                    url=f"https://github.com/org/repo/pull/{i + 1}",
                    head_branch=f"wt/branch-{i}",
                    base_branch="main",
                )
                repos.upsert_pull_request(tmpdir, record)
            prs = repos.list_pull_requests(tmpdir, "wt-list")
            self.assertEqual(len(prs), 3)

    def test_update_pull_request_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            _create_worktree(tmpdir, "wt-state")
            record = PullRequestRecord(
                id="pr-state",
                worktree_id="wt-state",
                number=99,
                title="State PR",
                state="open",
                url="https://github.com/org/repo/pull/99",
                head_branch="wt/state",
                base_branch="main",
            )
            repos.upsert_pull_request(tmpdir, record)
            repos.update_pull_request_state(
                tmpdir, "wt-state", 99, "merged", merged_at="2025-01-01T00:00:00Z"
            )
            fetched = repos.get_pull_request(tmpdir, "wt-state", 99)
            self.assertEqual(fetched.state, "merged")
            self.assertIsNotNone(fetched.merged_at)

    def test_delete_pull_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            _create_worktree(tmpdir, "wt-del")
            record = PullRequestRecord(
                id="pr-del",
                worktree_id="wt-del",
                number=88,
                title="Delete PR",
                state="open",
                url="https://github.com/org/repo/pull/88",
                head_branch="wt/delete",
                base_branch="main",
            )
            repos.upsert_pull_request(tmpdir, record)
            repos.delete_pull_request(tmpdir, "wt-del", 88)
            fetched = repos.get_pull_request(tmpdir, "wt-del", 88)
            self.assertIsNone(fetched)


class TestPullRequestDraftAndMergeable(unittest.TestCase):
    def test_draft_pr_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            _create_worktree(tmpdir, "wt-draft")
            record = PullRequestRecord(
                id="pr-draft",
                worktree_id="wt-draft",
                number=77,
                title="Draft PR",
                state="open",
                url="https://github.com/org/repo/pull/77",
                head_branch="wt/draft",
                base_branch="main",
                draft=True,
            )
            repos.upsert_pull_request(tmpdir, record)
            fetched = repos.get_pull_request(tmpdir, "wt-draft", 77)
            self.assertTrue(fetched.draft)

    def test_mergeable_states_persist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            init_db(tmpdir)
            for i, mergeable in enumerate([True, False, None]):
                wt_id = f"wt-merge-{i}"
                _create_worktree(tmpdir, wt_id)
                record = PullRequestRecord(
                    id=f"pr-merge-{i}",
                    worktree_id=wt_id,
                    number=60 + i,
                    title=f"Mergeable {i}",
                    state="open",
                    url=f"https://github.com/org/repo/pull/{60 + i}",
                    head_branch=f"wt/merge-{i}",
                    base_branch="main",
                    mergeable=mergeable,
                )
                repos.upsert_pull_request(tmpdir, record)
                fetched = repos.get_pull_request(tmpdir, wt_id, 60 + i)
                self.assertEqual(fetched.mergeable, mergeable)


if __name__ == "__main__":
    unittest.main()
