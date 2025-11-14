# blastengine_mailer

**作成者:** r3-yamauchi  
**バージョン:** 0.0.1  
**タイプ:** tool

[English](https://github.com/r3-yamauchi/dify-blastengine-mailer-plugin/blob/main/README.md) | 日本語

## 概要

`blastengine_mailer` は、Blastengine メールサービスの REST API を直接呼び出す Dify ワークフロー用プラグインです。公式 Python SDK を使用せず、添付ファイル付きのトランザクション/バルクメールを送信できます。`requests` ライブラリを使用して Blastengine API を直接呼び出すため、外部パッケージのインストールが制限された Dify 環境でも動作します。

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/r3-yamauchi/dify-blastengine-mailer-plugin)

## 特長

- **2種類のツール**: `send_transactional_email` (即時送信、CC/BCC対応) と `send_bulk_email` (CSV対応のキャンペーン) のみを提供し、用途を明確化。
- **添付ファイル対応**: メールへの添付ファイル機能を完全サポート（最大10件、合計1MBまで）。
- **直接 REST API 呼び出し**: 公式 Blastengine SDK への依存なし。リトライロジックとレート制限ハンドリングを内蔵した HTTP クライアントを使用。
- **添付ガードレール**: 禁止拡張子（.exe/.bat/.js/.vbs/.zip/.gz/.dll/.scr）を事前にブロックし、1通あたり最大10件・合計1MBまでに制限。
- **宛先バリデーション**: トランザクションは最大10件（TO、CC、BCCそれぞれ）、バルクは最大50件＋CSV入力に対応。重複や空行は自動除去。
- **セキュリティ**: デバッグログを適切にサニタイズし、本番環境での機密情報漏洩を防止。
- **資格情報チェック**: `login_id` / `api_key` を Provider 設定時に検証し、初期化エラーを早期発見。
- **テスト容易性**: pytest で HTTP リクエストをスタブ化し、ローカルで安全に挙動確認が可能。

## 前提条件

- プラグイン機能が有効な Dify インスタンス
- Blastengine アカウントと API 利用権限
- ログインID (`login_id`) と APIキー (`api_key`)
- 任意: 既定の From アドレス/名前

## プロバイダー設定

| キー | 必須 | 説明 |
| --- | --- | --- |
| `login_id` | ✅ | Blastengine 管理画面のログインID。
| `api_key` | ✅ | REST API認証に使用するAPIキー。
| `default_from_address` | ❌ | ツール全体の既定Fromアドレス。
| `default_from_name` | ❌ | From表示名の既定値。

## ツール

### `send_transactional_email`
- 内容: 単一の即時配信メールを送信。テキスト/HTMLどちらか一方は必須。CC/BCC対応。
- 入力: `to`(≤10件), `cc`(≤10件), `bcc`(≤10件), `subject`, `text_body`/`html_body`, `attachments`(≤10件, 合計≤1MB), `custom_headers`, `reply_to`。
- 出力: `delivery_id`, 宛先サマリー（TO、CC、BCC含む）, 添付サマリー。

### `send_bulk_email`
- 内容: `Bulk.begin()`→宛先投入→`bulk.update()`→`bulk.send([schedule_at])` を一括実行。宛先は配列とCSVの併用可。
- 入力: `subject`, `text_body`/`html_body`, `recipients`(≤50件) と/または `recipients_file`(単一列CSV), `schedule_at`(未来のISO8601), `attachments`。
- 出力: `delivery_id`, 宛先件数, 予約時刻の有無。

## インストール手順

1. リポジトリを取得し、Dify にプラグインとしてアップロード。
2. Provider タブで `login_id` / `api_key` などを設定。
3. ワークフロー内のツールノードに入力/ファイルをマッピング。
4. テスト配信時は Blastengine のテストドメインを使用し、本番キーと混在させないよう注意。

## テスト

- `python3 -m pytest tests` でユニットテストを実行可能。
- テストでは `dify_plugin` と HTTP リクエストのスタブを利用し、添付チェックやCSV読込・予約送信パラメータを検証しています。実際のネットワーク接続や認証情報は不要です。

## ライセンス

MIT License。レポジトリは [github.com/r3-yamauchi/dify-blastengine-mailer-plugin](https://github.com/r3-yamauchi/dify-blastengine-mailer-plugin) で公開予定です。
