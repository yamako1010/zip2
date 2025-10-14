from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from supabase import Client


CUSTOM_CLIENT_KEY = "custom"

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_FILE = DATA_DIR / "clients.json"

DEFAULT_CLIENTS = [
    {"key": "am", "name": "AMさま", "prefix": "AMS_KTC"},
    {"key": "af", "name": "AFさま", "prefix": "KTC_SSP"},
]

_SUPABASE: Client | None = None


class PasswordRuleError(ValueError):
    """Raised when password generation input is invalid."""


def set_supabase_client(client: Client | None) -> None:
    """Inject Supabase client at runtime."""
    global _SUPABASE
    _SUPABASE = client


def supabase_enabled() -> bool:
    return _SUPABASE is not None


def _format_supabase_client(row: dict[str, Any]) -> dict[str, str]:
    return {
        "key": row.get("id", ""),
        "name": row.get("name", ""),
        "prefix": row.get("prefix", ""),
    }


def _ensure_supabase_defaults() -> None:
    if not supabase_enabled():
        return

    try:
        existing = (
            _SUPABASE.table("clients")
            .select("name")
            .in_("name", [client["name"] for client in DEFAULT_CLIENTS])
            .execute()
        )
        existing_names = {row["name"] for row in existing.data or []}
        missing = [
            {"name": client["name"], "prefix": client["prefix"]}
            for client in DEFAULT_CLIENTS
            if client["name"] not in existing_names
        ]
        if missing:
            _SUPABASE.table("clients").insert(missing).execute()
    except Exception as exc:  # pragma: no cover - Supabase runtime issues
        logging.getLogger(__name__).warning(
            "Supabase default seeding failed: %s", exc
        )


def format_mmdd(target_date: date) -> str:
    """Return the MMDD string for the provided date."""
    return target_date.strftime("%m%d")


def ensure_data_file() -> None:
    """Ensure the fallback JSON storage exists with default data."""
    if DATA_FILE.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(DEFAULT_CLIENTS, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_clients_from_supabase() -> list[dict[str, str]]:
    if not supabase_enabled():
        raise PasswordRuleError("Supabase が初期化されていません。")

    try:
        response = (
            _SUPABASE.table("clients")
            .select("id,name,prefix")
            .order("name")
            .execute()
        )
    except Exception as exc:
        raise PasswordRuleError("クライアント情報の取得に失敗しました。") from exc

    data = response.data or []
    formatted = []
    for row in data:
        if not row.get("id"):
            continue
        formatted.append(_format_supabase_client(row))
    return formatted


def _load_clients_from_file() -> list[dict[str, str]]:
    try:
        ensure_data_file()
    except OSError:
        return [deepcopy(entry) for entry in DEFAULT_CLIENTS]

    try:
        data_text = DATA_FILE.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return [deepcopy(entry) for entry in DEFAULT_CLIENTS]

    try:
        data = json.loads(data_text)
    except json.JSONDecodeError as exc:
        raise PasswordRuleError("クライアント設定ファイルが壊れています。") from exc

    if not isinstance(data, list):
        raise PasswordRuleError("クライアント設定ファイルの形式が不正です。")

    return [deepcopy(entry) for entry in data]


def load_clients() -> list[dict[str, str]]:
    """Load client records from Supabase when available, fallback to local file."""
    if supabase_enabled():
        _ensure_supabase_defaults()
        clients = _load_clients_from_supabase()
        if clients:
            return clients
    return _load_clients_from_file()


def save_clients(clients: list[dict[str, str]]) -> None:
    """Persist client records to fallback storage only."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(clients, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        raise PasswordRuleError(
            "クライアント情報を保存できません。サーバーの書き込み権限を確認してください。"
        ) from exc


def _casefold(value: str) -> str:
    return (value or "").casefold()


def _validate_client_inputs(name: str, prefix: str) -> tuple[str, str]:
    trimmed_name = (name or "").strip()
    trimmed_prefix = (prefix or "").strip()
    if not trimmed_name:
        raise PasswordRuleError("クライアント名を入力してください。")
    if not trimmed_prefix:
        raise PasswordRuleError("接頭語を入力してください。")
    return trimmed_name, trimmed_prefix


def _ensure_unique(
    name: str, prefix: str, clients: Iterable[dict[str, str]]
) -> None:
    name_fold = _casefold(name)
    prefix_fold = _casefold(prefix)
    for client in clients:
        if _casefold(client.get("name")) == name_fold:
            raise PasswordRuleError(f"{name} は既に登録されています。")
        if _casefold(client.get("prefix")) == prefix_fold:
            raise PasswordRuleError(f"{prefix} は既に登録されています。")


def add_client_rule(name: str, prefix: str) -> dict[str, object]:
    """Add a new client rule using Supabase when available."""
    trimmed_name, trimmed_prefix = _validate_client_inputs(name, prefix)
    clients = load_clients()

    try:
        _ensure_unique(trimmed_name, trimmed_prefix, clients)
    except PasswordRuleError as err:
        return {
            "created": False,
            "client": next(
                (client for client in clients if client["name"] == trimmed_name), None
            ),
            "message": str(err),
        }

    if supabase_enabled():
        try:
            response = (
                _SUPABASE.table("clients")
                .insert({"name": trimmed_name, "prefix": trimmed_prefix})
                .execute()
            )
        except Exception as exc:
            raise PasswordRuleError("クライアントの保存に失敗しました。") from exc

        data = response.data[0] if response.data else {}
        client_entry = _format_supabase_client(
            data or {"name": trimmed_name, "prefix": trimmed_prefix}
        )
    else:
        existing_keys = {client["key"] for client in clients}
        new_key = _generate_key(trimmed_name, trimmed_prefix, existing_keys)
        client_entry = {"key": new_key, "name": trimmed_name, "prefix": trimmed_prefix}
        clients.append(client_entry)
        save_clients(clients)

    return {
        "created": True,
        "client": client_entry,
        "message": f"{trimmed_name} を追加しました。",
    }


def generate_password(client_key: str, target_date: date) -> str:
    """Generate password using the fixed rule for the specified client and date."""
    if supabase_enabled():
        try:
            response = (
                _SUPABASE.table("clients")
                .select("id,name,prefix")
                .eq("id", client_key)
                .execute()
            )
        except Exception as exc:
            raise PasswordRuleError("クライアント情報の取得に失敗しました。") from exc

        data = response.data or []
        if not data:
            raise PasswordRuleError(f"未対応のクライアントです: {client_key}")
        client = _format_supabase_client(data[0])
    else:
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


def delete_client_rule(key: str) -> dict[str, object]:
    """Delete a client rule identified by key."""
    normalized_key = (key or "").strip()
    if not normalized_key:
        raise PasswordRuleError("削除するクライアントを選択してください。")
    if normalized_key == CUSTOM_CLIENT_KEY:
        raise PasswordRuleError("Custom は削除できません。")

    if supabase_enabled():
        try:
            response = (
                _SUPABASE.table("clients")
                .select("id,name,prefix")
                .eq("id", normalized_key)
                .execute()
            )
        except Exception as exc:
            raise PasswordRuleError("クライアント情報の取得に失敗しました。") from exc

        data = response.data or []
        if not data:
            raise PasswordRuleError("指定されたクライアントは存在しません。")
        removed_client = _format_supabase_client(data[0])
        try:
            _SUPABASE.table("clients").delete().eq("id", normalized_key).execute()
        except Exception as exc:
            raise PasswordRuleError("クライアントの削除に失敗しました。") from exc
        return {
            "deleted": True,
            "client": removed_client,
            "message": f"{removed_client['name']} を削除しました。",
        }

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
