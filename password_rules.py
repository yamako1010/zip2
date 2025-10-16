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

DEFAULT_SUFFIX_RULE = "日付（月と日）"
DEFAULT_CLIENTS = [
    {"key": "am", "name": "AM様", "prefix": "AMS_KTC", "suffix_rule": DEFAULT_SUFFIX_RULE},
    {"key": "af", "name": "AF様", "prefix": "KTC_SSP", "suffix_rule": DEFAULT_SUFFIX_RULE},
]

_SUPABASE: Client | None = None
LOGGER = logging.getLogger(__name__)


class PasswordRuleError(ValueError):
    """Raised when password generation input is invalid."""


def set_supabase_client(client: Client | None) -> None:
    """Inject Supabase client at runtime and run setup tasks."""
    global _SUPABASE
    _SUPABASE = client
    if client is None:
        return

    try:
        _synchronize_fallback_clients(client)
    except Exception as exc:  # pragma: no cover - defensive guard
        LOGGER.warning("Supabase 初期化処理に失敗しました: %s", exc)


def supabase_enabled() -> bool:
    return _SUPABASE is not None


def _normalize_suffix_rule(value: str | None) -> str:
    text = (value or "").strip()
    return text or DEFAULT_SUFFIX_RULE


def _split_statements(sql: str) -> list[str]:
    """Split SQL statements by semicolon while keeping order."""
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def ensure_clients_table(client: Client) -> None:
    """Ensure the Supabase clients table exists with required columns."""
    try:
        client.table("clients").select("id").limit(1).execute()
        table_exists = True
    except Exception as exc:  # pragma: no cover - relies on Supabase runtime
        message = str(exc).lower()
        table_exists = "does not exist" not in message and "not exist" not in message
        if table_exists:
            # Unexpected error while probing; re-raise so caller can log.
            raise

        statements = _split_statements(
            """
            create table if not exists public.clients (
                id uuid primary key default gen_random_uuid(),
                name text not null,
                prefix text not null,
                suffix_rule text,
                created_at timestamptz not null default timezone('utc', now())
            );
            create unique index if not exists clients_name_lower_idx on public.clients (lower(name));
            create unique index if not exists clients_prefix_lower_idx on public.clients (lower(prefix));
            """
        )

        postgres = getattr(client, "postgres", None)
        if postgres is None:
            raise RuntimeError("Supabase postgres API が利用できません。") from exc

        for statement in statements:
            postgres.execute(statement)

    # Ensure optional columns exist when probing succeeded.
    statements = [
        "alter table public.clients add column if not exists suffix_rule text",
        (
            "alter table public.clients add column if not exists created_at "
            "timestamptz not null default timezone('utc', now())"
        ),
    ]

    postgres = getattr(client, "postgres", None)
    if postgres is None:
        return

    for statement in statements:
        try:
            postgres.execute(statement)
        except Exception:  # pragma: no cover - best-effort schema sync
            LOGGER.debug("Failed to apply schema patch: %s", statement, exc_info=True)


def _synchronize_fallback_clients(client: Client) -> None:
    """Seed Supabase with local fallback clients without duplicating."""
    try:
        response = client.table("clients").select("name,prefix").execute()
        existing_rows = response.data or []
    except Exception as exc:  # pragma: no cover - Supabase runtime issues
        LOGGER.warning("Supabase クライアント一覧取得に失敗: %s", exc)
        return

    existing_names = {_casefold(row.get("name")) for row in existing_rows}
    existing_prefixes = {_casefold(row.get("prefix")) for row in existing_rows}

    try:
        fallback_clients = _load_clients_from_file()
    except PasswordRuleError:
        fallback_clients = [deepcopy(entry) for entry in DEFAULT_CLIENTS]

    to_insert: list[dict[str, Any]] = []
    for client_row in fallback_clients:
        name = client_row.get("name")
        prefix = client_row.get("prefix")
        suffix_rule = _normalize_suffix_rule(client_row.get("suffix_rule"))

        if not name or not prefix:
            continue

        if _casefold(name) in existing_names or _casefold(prefix) in existing_prefixes:
            continue

        to_insert.append(
            {
                "name": name,
                "prefix": prefix,
                "suffix_rule": suffix_rule,
            }
        )

    if not to_insert:
        return

    try:
        client.table("clients").insert(to_insert).execute()
    except Exception as exc:  # pragma: no cover - Supabase runtime issues
        LOGGER.warning("Supabase 初期データ挿入に失敗: %s", exc)


def _format_supabase_client(row: dict[str, Any]) -> dict[str, str]:
    return {
        "key": row.get("id", ""),
        "name": row.get("name", ""),
        "prefix": row.get("prefix", ""),
        "suffix_rule": row.get("suffix_rule") or DEFAULT_SUFFIX_RULE,
    }


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
            .select("id,name,prefix,suffix_rule")
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

    results: list[dict[str, str]] = []
    for entry in data:
        copied = deepcopy(entry)
        copied.setdefault("suffix_rule", DEFAULT_SUFFIX_RULE)
        results.append(copied)
    return results


def load_clients() -> list[dict[str, str]]:
    """Load client records from Supabase when available, fallback to local file."""
    if supabase_enabled():
        return _load_clients_from_supabase()
    return _load_clients_from_file()


def save_clients(clients: list[dict[str, str]]) -> None:
    """Persist client records to fallback storage only."""
    serialized = []
    for client in clients:
        entry = {
            "key": client.get("key", ""),
            "name": client.get("name", ""),
            "prefix": client.get("prefix", ""),
            "suffix_rule": _normalize_suffix_rule(client.get("suffix_rule")),
        }
        serialized.append(entry)

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8"
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
    name: str,
    prefix: str,
    clients: Iterable[dict[str, str]],
    *,
    exclude_key: str | None = None,
) -> None:
    name_fold = _casefold(name)
    prefix_fold = _casefold(prefix)
    for client in clients:
        if exclude_key and _casefold(client.get("key")) == _casefold(exclude_key):
            continue

        if _casefold(client.get("name")) == name_fold:
            raise PasswordRuleError(f"{name} は既に登録されています。")
        if _casefold(client.get("prefix")) == prefix_fold:
            raise PasswordRuleError(f"{prefix} は既に登録されています。")


def add_client_rule(name: str, prefix: str, suffix_rule: str | None = None) -> dict[str, object]:
    """Add a new client rule using Supabase when available."""
    trimmed_name, trimmed_prefix = _validate_client_inputs(name, prefix)
    normalized_suffix = _normalize_suffix_rule(suffix_rule)
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
                .insert(
                    {
                        "name": trimmed_name,
                        "prefix": trimmed_prefix,
                        "suffix_rule": normalized_suffix,
                    }
                )
                .execute()
            )
        except Exception as exc:
            raise PasswordRuleError("クライアントの保存に失敗しました。") from exc

        data = response.data[0] if response.data else {}
        client_entry = _format_supabase_client(
            data
            or {
                "name": trimmed_name,
                "prefix": trimmed_prefix,
                "suffix_rule": normalized_suffix,
            }
        )
    else:
        existing_keys = {client["key"] for client in clients}
        new_key = _generate_key(trimmed_name, trimmed_prefix, existing_keys)
        client_entry = {
            "key": new_key,
            "name": trimmed_name,
            "prefix": trimmed_prefix,
            "suffix_rule": normalized_suffix,
        }
        clients.append(client_entry)
        save_clients(clients)

    return {
        "created": True,
        "client": client_entry,
        "message": f"{trimmed_name} を追加しました。",
    }


def update_client_rule(
    key: str, name: str, prefix: str, suffix_rule: str | None = None
) -> dict[str, object]:
    """Update an existing client rule."""
    normalized_key = (key or "").strip()
    if not normalized_key:
        raise PasswordRuleError("更新するクライアントを選択してください。")

    trimmed_name, trimmed_prefix = _validate_client_inputs(name, prefix)
    normalized_suffix = _normalize_suffix_rule(suffix_rule)

    clients = load_clients()
    _ensure_unique(
        trimmed_name,
        trimmed_prefix,
        clients,
        exclude_key=normalized_key,
    )

    if supabase_enabled():
        try:
            existing_response = (
                _SUPABASE.table("clients")
                .select("id,name,prefix,suffix_rule")
                .eq("id", normalized_key)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise PasswordRuleError("クライアント情報の取得に失敗しました。") from exc

        existing_rows = existing_response.data or []
        if not existing_rows:
            raise PasswordRuleError("指定されたクライアントは存在しません。")

        try:
            _SUPABASE.table("clients").update(
                {
                    "name": trimmed_name,
                    "prefix": trimmed_prefix,
                    "suffix_rule": normalized_suffix,
                }
            ).eq("id", normalized_key).execute()
        except Exception as exc:
            raise PasswordRuleError("クライアントの更新に失敗しました。") from exc

        updated_client = {
            "key": normalized_key,
            "name": trimmed_name,
            "prefix": trimmed_prefix,
            "suffix_rule": normalized_suffix,
        }
    else:
        target_client = None
        for entry in clients:
            if entry.get("key") == normalized_key:
                target_client = entry
                break

        if not target_client:
            raise PasswordRuleError("指定されたクライアントは存在しません。")

        target_client.update(
            {
                "name": trimmed_name,
                "prefix": trimmed_prefix,
                "suffix_rule": normalized_suffix,
            }
        )
        save_clients(clients)
        updated_client = target_client

    return {
        "updated": True,
        "client": updated_client,
        "message": f"{trimmed_name} を更新しました。",
    }


def generate_password(client_key: str, target_date: date) -> str:
    """Generate password using the fixed rule for the specified client and date."""
    if supabase_enabled():
        try:
            response = (
                _SUPABASE.table("clients")
                .select("id,name,prefix,suffix_rule")
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
            "rule": f"{client['prefix']} + {client.get('suffix_rule') or DEFAULT_SUFFIX_RULE}",
            "prefix": client["prefix"],
            "suffix_rule": client.get("suffix_rule") or DEFAULT_SUFFIX_RULE,
        }
        for client in load_clients()
    ]
    clients.append(
        {
            "key": CUSTOM_CLIENT_KEY,
            "label": "Custom（自由入力）",
            "rule": "自由入力 + 任意の日付(YYYYMMDD)",
            "suffix_rule": "",
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
                .select("id,name,prefix,suffix_rule")
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
