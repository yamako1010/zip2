from __future__ import annotations

import io
from datetime import date, datetime
from itertools import count
from pathlib import Path
from typing import Any

import pyzipper
from flask import Flask, jsonify, render_template, request, send_file, session
from supabase import Client, create_client
from werkzeug.utils import secure_filename

from password_rules import (
    CUSTOM_CLIENT_KEY,
    DEFAULT_CLIENTS,
    PasswordRuleError,
    add_client_rule,
    build_custom_password,
    delete_client_rule,
    generate_password,
    get_available_clients,
    set_supabase_client,
)

try:
    from config import (
        ADMIN_PASSWORD,
        FLASK_SECRET,
        LOGIN_PASSWORD,
        SESSION_COOKIE_SAMESITE,
        SESSION_COOKIE_SECURE,
        SUPABASE_SERVICE_ROLE_KEY,
        SUPABASE_URL,
    )
except ImportError as exc:  # pragma: no cover - ensures clearer error for missing config
    raise RuntimeError("config.py が見つかりません。管理者パスワードを設定してください。") from exc


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = Flask(
    __name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR)
)
MAX_UPLOAD_ARCHIVE_SIZE = 512 * 1024 * 1024  # 512MB

app.secret_key = FLASK_SECRET
app.config.update(
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE=SESSION_COOKIE_SAMESITE,
    MAX_CONTENT_LENGTH=MAX_UPLOAD_ARCHIVE_SIZE,
)
app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)

resolved_path = Path(__file__).resolve()
app.logger.info("[MonoZip] Using app.py at: %s", resolved_path)
app.logger.info("[MonoZip] templates -> %s", TEMPLATES_DIR)
app.logger.info("[MonoZip] static -> %s", STATIC_DIR)

supabase_client: Client | None = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        app.logger.info("[MonoZip] Supabase client initialized.")
    except Exception as exc:  # pragma: no cover - runtime safeguard
        app.logger.exception("Supabase クライアントの初期化に失敗しました: %s", exc)
else:
    app.logger.warning(
        "[MonoZip] Supabase 設定が見つかりません。ローカルの JSON 設定を使用します。"
    )

set_supabase_client(supabase_client)
if supabase_client:
    try:
        get_available_clients()
    except PasswordRuleError as exc:
        app.logger.warning("Supabase 初期データ取得に失敗しました: %s", exc)


def _build_default_client_payload() -> list[dict[str, str]]:
    """Return default clients formatted for UI when storage is unavailable."""
    clients = [
        {
            "key": client["key"],
            "label": client["name"],
            "rule": f"{client['prefix']} + MMDD",
            "prefix": client["prefix"],
        }
        for client in DEFAULT_CLIENTS
    ]
    clients.append(
        {
            "key": CUSTOM_CLIENT_KEY,
            "label": "Custom（自由入力）",
            "rule": "自由入力 + 任意の日付(YYYYMMDD)",
        }
    )
    return clients


def parse_date(value: str | None) -> date:
    """Parse YYYY-MM-DD strings into date objects. Defaults to today if missing."""
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise PasswordRuleError("日付は YYYY-MM-DD 形式で入力してください。") from exc


_PUBLIC_PATHS = {"/login", "/logout"}
_PUBLIC_PREFIXES = ("/static/", "/favicon.ico", "/api/public/")


@app.before_request
def enforce_authentication():
    if request.method == "OPTIONS":
        return None

    path = request.path
    if path in _PUBLIC_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return None

    if session.get("auth"):
        return None

    if request.accept_mimetypes.best == "application/json":
        return jsonify({"error": "unauthorized"}), 401

    return render_template("login.html"), 401


@app.get("/login")
def login_form() -> Any:
    if session.get("auth"):
        return render_template("index.html")
    return render_template("login.html")


@app.post("/login")
def login() -> Any:
    payload = request.get_json(silent=True) if request.is_json else None
    password_value = (
        payload.get("password") if isinstance(payload, dict) else request.form.get("password")
    )
    if (password_value or "").strip() == LOGIN_PASSWORD:
        session["auth"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "invalid password"}), 403


@app.post("/logout")
def logout() -> Any:
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/clients")
def list_clients() -> Any:
    fallback_used = False
    try:
        clients = get_available_clients()
    except PasswordRuleError as err:
        app.logger.error("クライアント情報の取得に失敗: %s", err)
        clients = _build_default_client_payload()
        fallback_used = True
    except Exception as exc:  # pragma: no cover - defensive
        app.logger.exception("クライアント情報取得で予期しないエラー: %s", exc)
        clients = _build_default_client_payload()
        fallback_used = True

    response: dict[str, Any] = {"clients": clients}
    if fallback_used:
        response["fallback"] = True
    return jsonify(response)


@app.post("/api/generate")
def api_generate() -> Any:
    payload = request.get_json(force=True, silent=True) or {}

    client_key = payload.get("clientKey") or payload.get("client_key")
    raw_date = payload.get("date")
    custom_value = payload.get("customInput") or payload.get("custom_input")

    if not client_key:
        return jsonify({"error": "クライアントを選択してください。"}), 400

    try:
        if client_key == CUSTOM_CLIENT_KEY:
            target_date = parse_date(raw_date) if raw_date else None
            password = build_custom_password(custom_value, target_date)
        else:
            target_date = parse_date(raw_date)
            password = generate_password(client_key, target_date)
    except PasswordRuleError as err:
        app.logger.warning("パスワード生成エラー: %s", err)
        return jsonify({"error": str(err)}), 400

    date_value = target_date.isoformat() if target_date else None

    return jsonify({"password": password, "date": date_value})


@app.post("/api/add_client")
def api_add_client() -> Any:
    payload = request.get_json(force=True, silent=True) or {}

    name = (payload.get("name") or "").strip()
    prefix = (payload.get("prefix") or "").strip()
    admin_password = payload.get("admin_password") or payload.get("adminPassword")

    if not admin_password:
        app.logger.warning("管理者パスワード未入力でクライアント追加リクエストを受信")
        return (
            jsonify(
                {"success": False, "error": "管理者パスワードを入力してください。"}
            ),
            400,
        )

    if admin_password != ADMIN_PASSWORD:
        app.logger.warning("管理者パスワード不一致のためクライアント追加を拒否しました。")
        return (
            jsonify({"success": False, "error": "管理者パスワードが正しくありません。"}),
            403,
        )

    try:
        result = add_client_rule(name, prefix)
    except PasswordRuleError as err:
        app.logger.warning("クライアント追加エラー: %s", err)
        return jsonify({"success": False, "error": str(err)}), 400

    status = 200
    response: dict[str, Any] = {
        "success": result["created"],
        "message": result["message"],
        "client": result["client"],
    }
    if not result["created"]:
        response["notice"] = "既存のルールを再利用しました。"
    return jsonify(response), status


@app.post("/api/zip")
def api_zip() -> Any:
    app.logger.debug("/api/zip invoked via %s", request.method)

    form = request.form
    files = request.files.getlist("files")

    if not files:
        app.logger.warning("ZIP生成リクエストにファイルが含まれていません。")
        return jsonify({"error": "1つ以上のファイルを選択してください。"}), 400

    password = (form.get("password") or "").strip()
    if not password:
        app.logger.warning("ZIP生成リクエストでパスワード未入力。")
        return jsonify({"error": "パスワードを入力してください。"}), 400

    mode = (form.get("mode") or "aes").strip().lower()
    if mode not in {"aes", "zipcrypto"}:
        app.logger.warning("不正な暗号方式が指定されました: %s", mode)
        return jsonify({"error": "対応していない暗号方式が指定されました。"}), 400

    requested_name = (form.get("zip_name") or "").strip()
    normalized_name = secure_filename(requested_name) if requested_name else ""
    if normalized_name and not normalized_name.lower().endswith(".zip"):
        normalized_name = f"{normalized_name}.zip"
    if not normalized_name:
        normalized_name = f"monozip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    collected_files: list[tuple[str, bytes]] = []
    total_size = 0
    fallback_names = (f"file_{i}" for i in count(1))

    for storage in files:
        original_name = storage.filename or ""
        safe_name = secure_filename(original_name)
        if not safe_name:
            safe_name = next(fallback_names)

        try:
            storage.stream.seek(0)
            data = storage.read()
        finally:
            storage.close()

        if not data:
            continue

        total_size += len(data)
        if total_size > MAX_UPLOAD_ARCHIVE_SIZE:
            app.logger.warning(
                "ZIP生成リクエストがサイズ上限を超過: %d bytes", total_size
            )
            return (
                jsonify(
                    {
                        "error": "アップロード合計サイズが上限を超えています。",
                        "limit": MAX_UPLOAD_ARCHIVE_SIZE,
                    }
                ),
                413,
            )

        collected_files.append((safe_name, data))

    if not collected_files:
        app.logger.warning("ZIP生成リクエストに有効ファイルがありませんでした。")
        return jsonify({"error": "有効なファイルが選択されていません。"}), 400

    buffer = io.BytesIO()
    password_bytes = password.encode("utf-8")

    try:
        if mode == "aes":
            with pyzipper.AESZipFile(
                buffer,
                mode="w",
                compression=pyzipper.ZIP_DEFLATED,
                encryption=pyzipper.WZ_AES,
            ) as archive:
                archive.setpassword(password_bytes)
                archive.setencryption(pyzipper.WZ_AES, nbits=256)
                for filename, data in collected_files:
                    archive.writestr(filename, data)
        else:
            with pyzipper.ZipFile(
                buffer, mode="w", compression=pyzipper.ZIP_DEFLATED
            ) as archive:
                archive.setpassword(password_bytes)
                archive.setencryption(pyzipper.ZIP_CRYPTO)
                for filename, data in collected_files:
                    archive.writestr(filename, data)
    except Exception as exc:  # pragma: no cover - runtime safeguard
        app.logger.exception("ZIP生成に失敗しました: %s", exc)
        return jsonify({"error": "ZIPファイルの生成に失敗しました。"}), 500

    buffer.seek(0)
    app.logger.info(
        "ZIP生成成功: %s (%d files, %d bytes, mode=%s)",
        normalized_name,
        len(collected_files),
        total_size,
        mode,
    )
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=normalized_name,
        max_age=0,
    )


@app.post("/api/delete_client")
def api_delete_client() -> Any:
    payload = request.get_json(force=True, silent=True) or {}

    key = (payload.get("key") or "").strip()
    admin_password = payload.get("admin_password") or payload.get("adminPassword")

    if not admin_password:
        return (
            jsonify(
                {"success": False, "error": "管理者パスワードを入力してください。"}
            ),
            400,
        )

    if admin_password != ADMIN_PASSWORD:
        return (
            jsonify({"success": False, "error": "管理者パスワードが正しくありません。"}),
            403,
        )

    try:
        result = delete_client_rule(key)
    except PasswordRuleError as err:
        app.logger.warning("クライアント削除エラー: %s", err)
        return jsonify({"success": False, "error": str(err)}), 400

    return jsonify(
        {
            "success": True,
            "message": result["message"],
            "client": result["client"],
        }
    )


@app.get("/")
def root() -> Any:
    template_path = TEMPLATES_DIR / "index.html"
    app.logger.info("Rendering template: %s", template_path)
    return render_template("index.html")


@app.after_request
def add_cors_headers(response):
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault(
        "Access-Control-Allow-Headers", "Content-Type, Authorization"
    )
    response.headers.setdefault(
        "Access-Control-Allow-Methods", "GET, POST, OPTIONS"
    )
    return response


if __name__ == "__main__":
    print("Running Flask app from:", __file__)
    app.logger.info("[MonoZip] Starting development server from: %s", resolved_path)
    app.run(debug=True)
