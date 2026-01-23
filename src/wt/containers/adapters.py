from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ContainerInfo:
    id: str
    name: str
    image: str
    status: str
    ports: str
    created: str


class ContainerAdapter(ABC):
    @abstractmethod
    def run(
        self,
        name: str,
        image: str,
        command: Optional[str] = None,
        ports: Optional[dict[str, str]] = None,
        volumes: Optional[dict[str, str]] = None,
        environment: Optional[dict[str, str]] = None,
        network: Optional[str] = None,
        detach: bool = True,
    ) -> str:
        pass

    @abstractmethod
    def stop(self, name: str, timeout: int = 10) -> None:
        pass

    @abstractmethod
    def rm(self, name: str, force: bool = False) -> None:
        pass

    @abstractmethod
    def ps(
        self, name_filter: Optional[str] = None, all_containers: bool = False
    ) -> list[ContainerInfo]:
        pass

    @abstractmethod
    def logs(self, name: str, tail: int = 100) -> list[str]:
        pass

    @abstractmethod
    def exec(self, name: str, command: list[str]) -> subprocess.CompletedProcess[str]:
        pass

    @abstractmethod
    def exists(self, name: str) -> bool:
        pass

    @abstractmethod
    def is_running(self, name: str) -> bool:
        pass

    @abstractmethod
    def network_create(self, name: str) -> None:
        pass

    @abstractmethod
    def network_rm(self, name: str) -> None:
        pass

    @abstractmethod
    def network_exists(self, name: str) -> bool:
        pass


class DockerAdapter(ContainerAdapter):
    def __init__(self, binary: str = "docker"):
        self.binary = binary

    def run(
        self,
        name: str,
        image: str,
        command: Optional[str] = None,
        ports: Optional[dict[str, str]] = None,
        volumes: Optional[dict[str, str]] = None,
        environment: Optional[dict[str, str]] = None,
        network: Optional[str] = None,
        detach: bool = True,
    ) -> str:
        args = [self.binary, "run", "--name", name]

        if detach:
            args.append("-d")

        if ports:
            for host_port, container_port in ports.items():
                args.extend(["-p", f"{host_port}:{container_port}"])

        if volumes:
            for host_path, container_path in volumes.items():
                args.extend(["-v", f"{host_path}:{container_path}"])

        if environment:
            for key, value in environment.items():
                args.extend(["-e", f"{key}={value}"])

        if network:
            args.extend(["--network", network])

        args.append(image)

        if command:
            args.extend(command.split())

        result = self._run(args)
        return result.stdout.strip()

    def stop(self, name: str, timeout: int = 10) -> None:
        self._run([self.binary, "stop", "-t", str(timeout), name], check=False)

    def rm(self, name: str, force: bool = False) -> None:
        args = [self.binary, "rm"]
        if force:
            args.append("-f")
        args.append(name)
        self._run(args, check=False)

    def ps(
        self, name_filter: Optional[str] = None, all_containers: bool = False
    ) -> list[ContainerInfo]:
        args = [
            self.binary,
            "ps",
            "--format",
            "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}|{{.CreatedAt}}",
        ]
        if all_containers:
            args.append("-a")
        if name_filter:
            args.extend(["--filter", f"name={name_filter}"])

        result = self._run(args, check=False)
        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 6:
                containers.append(
                    ContainerInfo(
                        id=parts[0],
                        name=parts[1],
                        image=parts[2],
                        status=parts[3],
                        ports=parts[4],
                        created=parts[5],
                    )
                )
        return containers

    def logs(self, name: str, tail: int = 100) -> list[str]:
        result = self._run(
            [self.binary, "logs", "--tail", str(tail), name], check=False
        )
        output = result.stdout + result.stderr
        return output.strip().split("\n") if output.strip() else []

    def exec(self, name: str, command: list[str]) -> subprocess.CompletedProcess[str]:
        args = [self.binary, "exec", name] + command
        return self._run(args, check=False)

    def exists(self, name: str) -> bool:
        result = self._run(
            [
                self.binary,
                "ps",
                "-a",
                "--filter",
                f"name=^{name}$",
                "--format",
                "{{.Names}}",
            ],
            check=False,
        )
        return name in result.stdout.strip().split("\n")

    def is_running(self, name: str) -> bool:
        result = self._run(
            [self.binary, "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            check=False,
        )
        return name in result.stdout.strip().split("\n")

    def network_create(self, name: str) -> None:
        self._run([self.binary, "network", "create", name])

    def network_rm(self, name: str) -> None:
        self._run([self.binary, "network", "rm", name], check=False)

    def network_exists(self, name: str) -> bool:
        result = self._run(
            [
                self.binary,
                "network",
                "ls",
                "--filter",
                f"name=^{name}$",
                "--format",
                "{{.Name}}",
            ],
            check=False,
        )
        return name in result.stdout.strip().split("\n")

    def _run(
        self,
        args: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"container command failed: {result.stderr}")
        return result


class PodmanAdapter(DockerAdapter):
    def __init__(self) -> None:
        super().__init__(binary="podman")


def detect_runtime() -> Literal["docker", "podman"]:
    if shutil.which("docker"):
        return "docker"
    if shutil.which("podman"):
        return "podman"
    raise RuntimeError("no container runtime found (docker or podman)")


def get_adapter(runtime: Literal["docker", "podman", "auto"]) -> ContainerAdapter:
    if runtime == "auto":
        runtime = detect_runtime()

    if runtime == "docker":
        return DockerAdapter()
    elif runtime == "podman":
        return PodmanAdapter()
    else:
        raise RuntimeError(f"unsupported container runtime: {runtime}")
