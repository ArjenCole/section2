"""API key 的 keyring 存取。

key 只进系统钥匙串（Windows 凭据管理器 / macOS 钥匙串 / SecretService），
条目名 ``section2/<provider>``；严禁写进配置文件或工程文件。
"""

from __future__ import annotations

import keyring

_SERVICE = "section2"


def set_api_key(provider: str, key: str) -> None:
    keyring.set_password(_SERVICE, provider, key)


def get_api_key(provider: str) -> str:
    try:
        return keyring.get_password(_SERVICE, provider) or ""
    except keyring.errors.KeyringError:
        return ""


def delete_api_key(provider: str) -> None:
    try:
        keyring.delete_password(_SERVICE, provider)
    except keyring.errors.KeyringError:
        pass
