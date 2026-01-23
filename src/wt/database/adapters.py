from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class DatabaseAdapter(ABC):
    @abstractmethod
    def create(self, name: str) -> None:
        pass

    @abstractmethod
    def drop(self, name: str) -> None:
        pass

    @abstractmethod
    def exists(self, name: str) -> bool:
        pass

    @abstractmethod
    def snapshot(self, name: str, output_path: Path) -> None:
        pass

    @abstractmethod
    def restore(self, name: str, input_path: Path) -> None:
        pass

    @abstractmethod
    def clone(self, source: str, target: str) -> None:
        pass


class PostgresAdapter(DatabaseAdapter):
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def create(self, name: str) -> None:
        self._run(
            ["createdb", "-h", self.host, "-p", str(self.port), "-U", self.user, name]
        )

    def drop(self, name: str) -> None:
        self._run(
            [
                "dropdb",
                "-h",
                self.host,
                "-p",
                str(self.port),
                "-U",
                self.user,
                "--if-exists",
                name,
            ]
        )

    def exists(self, name: str) -> bool:
        result = self._run(
            [
                "psql",
                "-h",
                self.host,
                "-p",
                str(self.port),
                "-U",
                self.user,
                "-lqt",
                "-c",
                f"SELECT 1 FROM pg_database WHERE datname = '{name}'",
            ],
            check=False,
        )
        return name in result.stdout

    def snapshot(self, name: str, output_path: Path) -> None:
        with open(output_path, "w") as f:
            self._run(
                [
                    "pg_dump",
                    "-h",
                    self.host,
                    "-p",
                    str(self.port),
                    "-U",
                    self.user,
                    name,
                ],
                stdout=f,
            )

    def restore(self, name: str, input_path: Path) -> None:
        if not self.exists(name):
            self.create(name)
        with open(input_path, "r") as f:
            self._run(
                [
                    "psql",
                    "-h",
                    self.host,
                    "-p",
                    str(self.port),
                    "-U",
                    self.user,
                    "-d",
                    name,
                ],
                stdin=f,
            )

    def clone(self, source: str, target: str) -> None:
        self.drop(target)
        self._run(
            [
                "createdb",
                "-h",
                self.host,
                "-p",
                str(self.port),
                "-U",
                self.user,
                "-T",
                source,
                target,
            ]
        )

    def _run(
        self,
        args: list[str],
        check: bool = True,
        stdin=None,
        stdout=None,
    ) -> subprocess.CompletedProcess[str]:
        env = None
        if self.password:
            import os

            env = os.environ.copy()
            env["PGPASSWORD"] = self.password

        result = subprocess.run(
            args,
            env=env,
            stdin=stdin,
            stdout=stdout or subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"postgres command failed: {result.stderr}")
        return result


class SqliteAdapter(DatabaseAdapter):
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _db_path(self, name: str) -> Path:
        return self.base_dir / f"{name}.db"

    def create(self, name: str) -> None:
        path = self._db_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def drop(self, name: str) -> None:
        path = self._db_path(name)
        if path.exists():
            path.unlink()

    def exists(self, name: str) -> bool:
        return self._db_path(name).exists()

    def snapshot(self, name: str, output_path: Path) -> None:
        import shutil

        path = self._db_path(name)
        if path.exists():
            shutil.copy2(path, output_path)

    def restore(self, name: str, input_path: Path) -> None:
        import shutil

        path = self._db_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, path)

    def clone(self, source: str, target: str) -> None:
        import shutil

        source_path = self._db_path(source)
        target_path = self._db_path(target)
        if source_path.exists():
            shutil.copy2(source_path, target_path)
