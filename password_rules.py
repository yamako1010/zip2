from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy
from datetime import date


CUSTOM_CLIENT_KEY = "custom"

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "clients.json"

DEFAULT_CLIENTS = [
    {"key": "am", "name": "AMさま", "prefix": "AMS_KTC"},
    {"key": "af", "name": "AFさま", "prefix": "KTC_SSP"},
]


class PasswordRuleError(ValueError):
    """Raised when password generation input is invalid."""


def format_mmdd(target_date: date) -> str:
    """Return the MMDD string for the provided date."""
    return target_date.strftime("%m%d")


def ensure_data_file() -> None:
    """Ensure the client storage exists with default data."""
    if not DATA_FILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(DEFAULT_CLIENTS, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def load_clients() -> list[dict[str, str]]:
    """Load client records from storage."""
    ensure_data_file()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    # Defensive copy to avoid accidental mutation outside
    return [deepcopy(entry) for entry in data]


def save_clients(clients: list[dict[str, str]]) -> None:
    """Persist client records to storage."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(clients, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def generate_password(client_key: str, target_date: date) -> str:
    """Generate password using the fixed rule for the specified client and date."""
    clients = {client["key"]: client for client in load_clients()}
    client = clients.get(client_key)
    if not client:
        raise PasswordRuleError(f"未対応のクライアントです: {client_key}")

    prefix = client["prefix"]
    suffix = format_mmdd(target_date)
    return f"{prefix}{suffix}"


def get_available_clients() -> list[dict[str, str]]:
    """Return client metadata for UI consumption."""
    clients = [
        {
            "key": client["key"],
            "label": client["name"],
            "rule": f"{client['prefix']} + MMDD",
            "prefix": client["prefix"],
        }
        for client in load_clients()
    ]
    clients.append(
        {
            "key": CUSTOM_CLIENT_KEY,
            "label": "Custom（自由入力）",
            "rule": "自由入力 + 任意の日付(YYYYMMDD)",
        }
    )
    return clients


def build_custom_password(raw_value: str, target_date: date | None) -> str:
    """Compose a password from user-provided text and optional date."""
    user_input = (raw_value or "").strip()
    if not user_input:
        raise PasswordRuleError("自由入力のテキストを入力してください。")

    if not target_date:
        return user_input

    suffix = target_date.strftime("%Y%m%d")
    return f"{user_input}{suffix}"


def _generate_key(name: str, prefix: str, existing_keys: set[str]) -> str:
    """Generate a stable key from provided name/prefix."""
    base = "".join(ch for ch in name.lower() if ch.isalnum())
    if not base:
        base = "".join(ch for ch in prefix.lower() if ch.isalnum())
    if not base:
        base = "client"

    candidate = base
    counter = 1
    while candidate in existing_keys:
        counter += 1
        candidate = f"{base}{counter}"
    return candidate


def add_client_rule(name: str, prefix: str) -> dict[str, object]:
    """Add a new client rule or skip when duplicated."""
    trimmed_name = (name or "").strip()
    trimmed_prefix = (prefix or "").strip()

    if not trimmed_name:
        raise PasswordRuleError("クライアント名を入力してください。")
    if not trimmed_prefix:
        raise PasswordRuleError("接頭語を入力してください。")

    clients = load_clients()
    existing_keys = {client["key"] for client in clients}

    for client in clients:
        if client["name"].lower() == trimmed_name.lower():
            return {
                "created": False,
                "client": client,
                "message": f"{trimmed_name} は既に登録されています。",
            }
        if client["prefix"].lower() == trimmed_prefix.lower():
            return {
                "created": False,
                "client": client,
                "message": f"{trimmed_prefix} は既に登録されています。",
            }

    new_key = _generate_key(trimmed_name, trimmed_prefix, existing_keys)
    client_entry = {"key": new_key, "name": trimmed_name, "prefix": trimmed_prefix}
    clients.append(client_entry)
    save_clients(clients)

    return {
        "created": True,
        "client": client_entry,
        "message": f"{trimmed_name} を追加しました。",
    }


def delete_client_rule(key: str) -> dict[str, object]:
    """Delete a client rule identified by key."""
    normalized_key = (key or "").strip()
    if not normalized_key:
        raise PasswordRuleError("削除するクライアントを選択してください。")
    if normalized_key == CUSTOM_CLIENT_KEY:
        raise PasswordRuleError("Custom は削除できません。")

    clients = load_clients()
    remaining = []
    removed_client = None

    for client in clients:
        if client["key"] == normalized_key:
            removed_client = client
            continue
        remaining.append(client)

    if not removed_client:
        raise PasswordRuleError("指定されたクライアントは存在しません。")

    save_clients(remaining)
    return {
        "deleted": True,
        "client": removed_client,
        "message": f"{removed_client['name']} を削除しました。",
    }
