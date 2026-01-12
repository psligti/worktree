from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .api import (
    WorktreeMetadata,
    create_worktree,
    get_diffstat,
    get_recent_commits,
    get_worktree_by_task_id,
    list_worktrees,
    lock_worktree,
    open_in_editor,
    remove_worktree,
    run_command_in_worktree,
    unlock_worktree,
)
from .git_worktree import GitWorktreeError


class WorktreeMetadataModel(BaseModel):
    task_id: str
    path: str
    branch: Optional[str]
    purpose: Optional[str]
    head_sha: str
    locked: bool
    lock_reason: Optional[str]
    prunable: Optional[bool]
    prunable_reason: Optional[str]
    dirty: bool

    @classmethod
    def from_metadata(cls, metadata: WorktreeMetadata) -> "WorktreeMetadataModel":
        return cls(
            task_id=metadata.task_id,
            path=metadata.path,
            branch=metadata.branch,
            purpose=metadata.purpose,
            head_sha=metadata.head_sha,
            locked=metadata.locked,
            lock_reason=metadata.lock_reason,
            prunable=metadata.prunable,
            prunable_reason=metadata.prunable_reason,
            dirty=metadata.dirty,
        )


class CreateWorktreeRequest(BaseModel):
    task_id: str
    base: Optional[str] = None
    branch: Optional[str] = None
    path: Optional[str] = None
    detached: bool = False
    lock: bool = False
    lock_reason: Optional[str] = None


class LockRequest(BaseModel):
    reason: str


class RemoveRequest(BaseModel):
    force: bool = False


class RunRequest(BaseModel):
    command: str


class RunResponse(BaseModel):
    output: str


class CommitLogResponse(BaseModel):
    log: str


class DiffstatResponse(BaseModel):
    diffstat: str


def create_app() -> FastAPI:
    app = FastAPI(title="wt worktree api")

    @app.get("/worktrees", response_model=list[WorktreeMetadataModel])
    def list_worktrees_route() -> list[WorktreeMetadataModel]:
        try:
            rows = list_worktrees()
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return [WorktreeMetadataModel.from_metadata(row) for row in rows]

    @app.get("/worktrees/{task_id}", response_model=WorktreeMetadataModel)
    def get_worktree_route(task_id: str) -> WorktreeMetadataModel:
        try:
            row = get_worktree_by_task_id(task_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return WorktreeMetadataModel.from_metadata(row)

    @app.post("/worktrees", response_model=WorktreeMetadataModel)
    def create_worktree_route(payload: CreateWorktreeRequest) -> WorktreeMetadataModel:
        try:
            row = create_worktree(
                payload.task_id,
                base=payload.base,
                branch=payload.branch,
                path=payload.path,
                detached=payload.detached,
                lock=payload.lock,
                lock_reason=payload.lock_reason,
            )
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return WorktreeMetadataModel.from_metadata(row)

    @app.post("/worktrees/{task_id}/lock")
    def lock_worktree_route(task_id: str, payload: LockRequest) -> dict[str, str]:
        try:
            row = get_worktree_by_task_id(task_id)
            lock_worktree(row.path, payload.reason)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"status": "locked", "task_id": task_id}

    @app.post("/worktrees/{task_id}/unlock")
    def unlock_worktree_route(task_id: str) -> dict[str, str]:
        try:
            row = get_worktree_by_task_id(task_id)
            unlock_worktree(row.path)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"status": "unlocked", "task_id": task_id}

    @app.post("/worktrees/{task_id}/remove")
    def remove_worktree_route(task_id: str, payload: RemoveRequest) -> dict[str, str]:
        try:
            row = get_worktree_by_task_id(task_id)
            remove_worktree(row.path, force=payload.force)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"status": "removed", "task_id": task_id}

    @app.post("/worktrees/{task_id}/run", response_model=RunResponse)
    def run_worktree_route(task_id: str, payload: RunRequest) -> RunResponse:
        try:
            row = get_worktree_by_task_id(task_id)
            output = run_command_in_worktree(row.path, payload.command)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return RunResponse(output=output)

    @app.post("/worktrees/{task_id}/open-editor")
    def open_editor_route(task_id: str) -> dict[str, str]:
        try:
            row = get_worktree_by_task_id(task_id)
            open_in_editor(row.path)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"status": "opened", "task_id": task_id}

    @app.get("/worktrees/{task_id}/commits", response_model=CommitLogResponse)
    def commits_route(
        task_id: str,
        count: int = Query(5, ge=1, le=50),
    ) -> CommitLogResponse:
        try:
            row = get_worktree_by_task_id(task_id)
            log = get_recent_commits(row.path, count=count)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return CommitLogResponse(log=log)

    @app.get("/worktrees/{task_id}/diffstat", response_model=DiffstatResponse)
    def diffstat_route(task_id: str) -> DiffstatResponse:
        try:
            row = get_worktree_by_task_id(task_id)
            diffstat = get_diffstat(row.path)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except GitWorktreeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return DiffstatResponse(diffstat=diffstat)

    return app


def main() -> int:
    import uvicorn

    uvicorn.run("wt.api_server:create_app", host="127.0.0.1", port=8765, factory=True)
    return 0
