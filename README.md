# MonoZip Web

MonoZip Web は Supabase 永続化とログインゲートを備えた ZIP パスワード管理ツールです。以下の手順でローカル環境を構築し、Vercel デプロイにも同じ構成を反映してください。

## 必須環境変数
アプリ起動前にターミナル（または `.env`）で下記を設定します。

```
export FLASK_SECRET="十分に長いランダム文字列"
export ADMIN_PASSWORD="SSP"
export LOGIN_PASSWORD="SSP"
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="service_role_key"
# 任意: ローカル HTTP 実行時にセッション維持したい場合
export SESSION_COOKIE_SECURE=false
```

Vercel でも同じ名称で Environment Variables を登録してください。

## ローカル実行手順
1. `cd ~/Documents/Codex/ZIP2`
2. `python3.12 -m venv .venv`
3. `source .venv/bin/activate`（Windows: `.venv\Scripts\activate`）
4. `pip install -r requirements.txt`
5. 必須環境変数を設定後 `python app.py`
6. ブラウザで `http://127.0.0.1:5000` を開き、表示されるログイン画面で `LOGIN_PASSWORD` を入力

開発サーバーは `Ctrl+C` で停止できます。`./start_mac.sh` / `start_win.bat` は上記手順を自動化します。

## Supabase セットアップ
Supabase SQL Editor で以下を実行し、`clients` テーブルを用意します。

```sql
create table if not exists clients (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  prefix text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists clients_name_idx on clients (name);
```

初回アクセス時に AM/AF のデフォルトレコードが自動投入されます（既に存在する場合は挿入されません）。

## 機能概要
- **ログインゲート**: `/login` で認証成功するとセッションに `auth=true` を保存します。未ログイン時に保護リソースへアクセスするとログインページまたは JSON 401 を返します。
- **クライアント管理**: 管理フォームでは Supabase の `clients` テーブルを操作します。操作には `ADMIN_PASSWORD` が必要です。
- **パスワード生成**: 既存のパスワード生成ルールは維持され、Supabase から取得した接頭辞＋日付で生成します。Custom モードは自由入力＋日付（任意）です。
- **ZIP 作成**: フォームから複数ファイルを送信するとメモリ上で ZIP を生成して返却します。暗号方式は `AES`（高強度、7-Zip/WinZip 推奨）と `ZipCrypto`（Windows 標準互換）を切り替え可能です。

## テストチェックリスト
1. ローカルで `python app.py` → `/login` にアクセスし、`LOGIN_PASSWORD` でログインできること。
2. `/api/clients` が Supabase からクライアント一覧を取得し、UI に反映されること。
3. 管理フォームで新規クライアントの追加・削除ができること。
4. ZIP 作成フォームで AES / ZipCrypto の両モードが動作し、ウォーニング文言が表示されること。
5. Vercel デプロイ後（`https://zip2-eight.vercel.app/` 等）でも同じ挙動を確認すること。

## 注意事項
- セッション Cookie は既定で `Secure=True`/`SameSite=Lax` です。HTTP のままローカル検証する場合は `SESSION_COOKIE_SECURE=false` を設定してください。
- Supabase への書き込みは Service Role Key で行います。クライアント側（ブラウザ）には露出しません。
