from __future__ import annotations

from datetime import date, datetime
import io
from itertools import count
from pathlib import Path
from typing import Any

import pyzipper
from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from password_rules import (
    CUSTOM_CLIENT_KEY,
    PasswordRuleError,
    add_client_rule,
    build_custom_password,
    delete_client_rule,
    generate_password,
    get_available_clients,
)

try:
    from config import ADMIN_PASSWORD
except ImportError as exc:  # pragma: no cover - ensures clearer error for missing config
    raise RuntimeError("config.py が見つかりません。管理者パスワードを設定してください。") from exc


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR

app = Flask(__name__, static_folder=str(STATIC_DIR))
MAX_UPLOAD_ARCHIVE_SIZE = 512 * 1024 * 1024  # 512MB

resolved_path = Path(__file__).resolve()
print(f"Running Flask app from: {resolved_path}")
app.logger.info("[MonoZip] Using app.py at: %s", resolved_path)


def parse_date(value: str | None) -> date:
    """Parse YYYY-MM-DD strings into date objects. Defaults to today if missing."""
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise PasswordRuleError("日付は YYYY-MM-DD 形式で入力してください。") from exc


@app.get("/api/clients")
def list_clients() -> Any:
    clients = get_available_clients()
    return jsonify({"clients": clients})


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
        return (
            jsonify(
                {"success": False, "error": "管理者パスワードを入力してください。"}
            ),
            400,
        )

    if admin_password != ADMIN_PASSWORD:
        return (
            jsonify({"success": False, "error": "管理者パスワードが正しくありません。"}),
            401,
        )

    try:
        result = add_client_rule(name, prefix)
    except PasswordRuleError as err:
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


@app.route("/api/zip", methods=["GET", "POST"])
def api_zip() -> Any:
    print(f"Received method: {request.method}")
    app.logger.debug("/api/zip invoked via %s", request.method)
    if request.method != "POST":
        return jsonify({"error": "POST メソッドを使用してください。"}), 405

    form = request.form
    files = request.files.getlist("files")

    if not files:
        return jsonify({"error": "1つ以上のファイルを選択してください。"}), 400

    password = (form.get("password") or "").strip()
    password_confirm = (form.get("password_confirm") or "").strip()
    if not password or not password_confirm:
        return jsonify({"error": "パスワードと確認用パスワードを入力してください。"}), 400

    if password != password_confirm:
        return jsonify({"error": "パスワードが一致しません。"}), 400

    algo = (form.get("algo") or "AES-256").upper()
    if algo not in {"AES-256", "ZIPCRYPTO"}:
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

        data = storage.read()
        storage.close()

        if not data:
            continue

        total_size += len(data)
        if total_size > MAX_UPLOAD_ARCHIVE_SIZE:
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
        return jsonify({"error": "有効なファイルが選択されていません。"}), 400

    buffer = io.BytesIO()
    password_bytes = password.encode("utf-8")

    try:
        if algo == "AES-256":
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
        else:  # ZipCrypto
            with pyzipper.ZipFile(
                buffer, mode="w", compression=pyzipper.ZIP_DEFLATED
            ) as archive:
                archive.setpassword(password_bytes)
                for filename, data in collected_files:
                    archive.writestr(filename, data)
    except Exception as exc:  # pragma: no cover - runtime safeguard
        app.logger.exception("ZIP生成に失敗しました: %s", exc)
        return jsonify({"error": "ZIPファイルの生成に失敗しました。"}), 500

    buffer.seek(0)
    app.logger.info(
        "ZIP生成成功: %s (%d files, %d bytes, algo=%s)",
        normalized_name,
        len(collected_files),
        total_size,
        algo,
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
            401,
        )

    try:
        result = delete_client_rule(key)
    except PasswordRuleError as err:
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
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str) -> Any:
    return send_from_directory(STATIC_DIR, filename)


if __name__ == "__main__":
    app.run(debug=True)
