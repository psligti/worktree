from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Literal, Optional


class GitHubError(RuntimeError):
    pass


PullRequestState = Literal["open", "closed", "merged"]


@dataclass
class PullRequest:
    number: int
    title: str
    state: PullRequestState
    url: str
    head_branch: str
    base_branch: str
    draft: bool
    mergeable: Optional[bool] = None
    body: Optional[str] = None


class GitHubAdapter:
    def __init__(self, repo_root: str):
        self.repo_root = repo_root

    def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
        head: Optional[str] = None,
        draft: bool = False,
    ) -> PullRequest:
        args = [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
        ]
        if head:
            args.extend(["--head", head])
        if draft:
            args.append("--draft")

        result = self._run(args)
        url = result.stdout.strip()

        pr_number = self._extract_pr_number(url)
        return self.get_pr(pr_number)

    def get_pr(self, number: int) -> PullRequest:
        args = [
            "gh",
            "pr",
            "view",
            str(number),
            "--json",
            "number,title,state,url,headRefName,baseRefName,isDraft,mergeable,body",
        ]
        result = self._run(args)
        data = json.loads(result.stdout)
        return self._parse_pr(data)

    def get_pr_for_branch(self, branch: str) -> Optional[PullRequest]:
        args = [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--json",
            "number,title,state,url,headRefName,baseRefName,isDraft,mergeable,body",
            "--limit",
            "1",
        ]
        result = self._run(args, check=False)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        if not data:
            return None
        return self._parse_pr(data[0])

    def list_prs(
        self,
        state: Literal["open", "closed", "merged", "all"] = "open",
        limit: int = 30,
    ) -> list[PullRequest]:
        args = [
            "gh",
            "pr",
            "list",
            "--state",
            state,
            "--json",
            "number,title,state,url,headRefName,baseRefName,isDraft,mergeable,body",
            "--limit",
            str(limit),
        ]
        result = self._run(args)
        data = json.loads(result.stdout)
        return [self._parse_pr(item) for item in data]

    def merge_pr(
        self,
        number: int,
        strategy: Literal["merge", "squash", "rebase"] = "squash",
        delete_branch: bool = True,
    ) -> None:
        args = ["gh", "pr", "merge", str(number), f"--{strategy}"]
        if delete_branch:
            args.append("--delete-branch")
        self._run(args)

    def close_pr(self, number: int) -> None:
        self._run(["gh", "pr", "close", str(number)])

    def reopen_pr(self, number: int) -> None:
        self._run(["gh", "pr", "reopen", str(number)])

    def open_pr_in_browser(self, number: int) -> None:
        self._run(["gh", "pr", "view", str(number), "--web"])

    def pr_checks(self, number: int) -> list[dict[str, str]]:
        args = ["gh", "pr", "checks", str(number), "--json", "name,state,conclusion"]
        result = self._run(args, check=False)
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)

    def pr_ready(self, number: int) -> None:
        self._run(["gh", "pr", "ready", str(number)])

    def _run(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise GitHubError(f"gh command failed: {error_msg}")
        return result

    def _extract_pr_number(self, url: str) -> int:
        parts = url.rstrip("/").split("/")
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            raise GitHubError(f"could not extract PR number from: {url}")

    def _parse_pr(self, data: dict) -> PullRequest:
        state_raw = data.get("state", "OPEN").upper()
        if state_raw == "MERGED":
            state: PullRequestState = "merged"
        elif state_raw == "CLOSED":
            state = "closed"
        else:
            state = "open"

        mergeable_raw = data.get("mergeable")
        if mergeable_raw == "MERGEABLE":
            mergeable: Optional[bool] = True
        elif mergeable_raw == "CONFLICTING":
            mergeable = False
        else:
            mergeable = None

        return PullRequest(
            number=data["number"],
            title=data["title"],
            state=state,
            url=data["url"],
            head_branch=data["headRefName"],
            base_branch=data["baseRefName"],
            draft=data.get("isDraft", False),
            mergeable=mergeable,
            body=data.get("body"),
        )
