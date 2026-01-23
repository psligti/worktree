from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class SecretsAdapter(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        pass

    @abstractmethod
    def list_keys(self) -> list[str]:
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        pass


class EnvFileAdapter(SecretsAdapter):
    def __init__(self, env_file: Path):
        self.env_file = env_file

    def _load(self) -> dict[str, str]:
        if not self.env_file.exists():
            return {}
        result = {}
        for line in self.env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                result[key.strip()] = value.strip()
        return result

    def _save(self, secrets: dict[str, str]) -> None:
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"{key}={value}" for key, value in sorted(secrets.items())]
        self.env_file.write_text("\n".join(lines) + "\n" if lines else "")

    def get(self, key: str) -> Optional[str]:
        secrets = self._load()
        return secrets.get(key)

    def set(self, key: str, value: str) -> None:
        secrets = self._load()
        secrets[key] = value
        self._save(secrets)

    def delete(self, key: str) -> None:
        secrets = self._load()
        if key in secrets:
            del secrets[key]
            self._save(secrets)

    def list_keys(self) -> list[str]:
        return list(self._load().keys())

    def exists(self, key: str) -> bool:
        return key in self._load()


class EncryptedFileAdapter(SecretsAdapter):
    def __init__(self, encrypted_file: Path, key_file: Path):
        self.encrypted_file = encrypted_file
        self.key_file = key_file

    def _get_or_create_key(self) -> bytes:
        if self.key_file.exists():
            return base64.b64decode(self.key_file.read_text().strip())
        key = os.urandom(32)
        self.key_file.parent.mkdir(parents=True, exist_ok=True)
        self.key_file.write_text(base64.b64encode(key).decode())
        os.chmod(self.key_file, 0o600)
        return key

    def _xor_cipher(self, data: bytes, key: bytes) -> bytes:
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

    def _load(self) -> dict[str, str]:
        if not self.encrypted_file.exists():
            return {}
        key = self._get_or_create_key()
        encrypted = base64.b64decode(self.encrypted_file.read_text().strip())
        decrypted = self._xor_cipher(encrypted, key)
        try:
            return json.loads(decrypted.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _save(self, secrets: dict[str, str]) -> None:
        key = self._get_or_create_key()
        data = json.dumps(secrets).encode()
        encrypted = self._xor_cipher(data, key)
        self.encrypted_file.parent.mkdir(parents=True, exist_ok=True)
        self.encrypted_file.write_text(base64.b64encode(encrypted).decode())
        os.chmod(self.encrypted_file, 0o600)

    def get(self, key: str) -> Optional[str]:
        secrets = self._load()
        return secrets.get(key)

    def set(self, key: str, value: str) -> None:
        secrets = self._load()
        secrets[key] = value
        self._save(secrets)

    def delete(self, key: str) -> None:
        secrets = self._load()
        if key in secrets:
            del secrets[key]
            self._save(secrets)

    def list_keys(self) -> list[str]:
        return list(self._load().keys())

    def exists(self, key: str) -> bool:
        return key in self._load()


class KeyringAdapter(SecretsAdapter):
    def __init__(self, service_name: str):
        self.service_name = service_name
        self._keys_file: Optional[Path] = None

    def _get_keyring(self):
        try:
            import keyring

            return keyring
        except ImportError:
            raise RuntimeError("keyring package not installed")

    def _keys_path(self) -> Path:
        if self._keys_file is None:
            import tempfile

            self._keys_file = (
                Path(tempfile.gettempdir()) / f".wt-keyring-keys-{self.service_name}"
            )
        return self._keys_file

    def _load_keys(self) -> set[str]:
        path = self._keys_path()
        if not path.exists():
            return set()
        return (
            set(path.read_text().strip().split("\n"))
            if path.read_text().strip()
            else set()
        )

    def _save_keys(self, keys: set[str]) -> None:
        path = self._keys_path()
        path.write_text("\n".join(sorted(keys)))

    def get(self, key: str) -> Optional[str]:
        keyring = self._get_keyring()
        return keyring.get_password(self.service_name, key)

    def set(self, key: str, value: str) -> None:
        keyring = self._get_keyring()
        keyring.set_password(self.service_name, key, value)
        keys = self._load_keys()
        keys.add(key)
        self._save_keys(keys)

    def delete(self, key: str) -> None:
        keyring = self._get_keyring()
        try:
            keyring.delete_password(self.service_name, key)
        except keyring.errors.PasswordDeleteError:
            pass
        keys = self._load_keys()
        keys.discard(key)
        self._save_keys(keys)

    def list_keys(self) -> list[str]:
        return list(self._load_keys())

    def exists(self, key: str) -> bool:
        return self.get(key) is not None
