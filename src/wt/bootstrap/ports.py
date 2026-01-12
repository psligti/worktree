from __future__ import annotations

from ..persistence.db import connect
from ..persistence.repos import upsert_ports


DEFAULT_PORT_START = 3000
DEFAULT_PORT_END = 9000


def allocate_ports(repo_root: str, worktree_id: str, keys: list[str]) -> dict[str, int]:
    with connect(repo_root) as conn:
        existing = {
            row["key"]: int(row["port"])
            for row in conn.execute(
                "SELECT key, port FROM ports WHERE worktree_id = ?", (worktree_id,)
            ).fetchall()
        }
        used_ports = {int(row[0]) for row in conn.execute("SELECT port FROM ports").fetchall()}

    ports: dict[str, int] = dict(existing)
    for key in keys:
        if key in ports:
            continue
        port = _next_free_port(used_ports)
        ports[key] = port
        used_ports.add(port)

    upsert_ports(repo_root, worktree_id, ports)
    return ports


def _next_free_port(used_ports: set[int]) -> int:
    for port in range(DEFAULT_PORT_START, DEFAULT_PORT_END):
        if port not in used_ports:
            return port
    raise RuntimeError("no free ports available")
