# blastengine_mailer

**作成者:** r3-yamauchi  
**バージョン:** 0.0.1  
**タイプ:** tool

[English](https://github.com/r3-yamauchi/dify-blastengine-mailer-plugin/blob/main/README.md) | 日本語

> ⚠️ **注意: このプラグインは非公式です**  
> このプラグインは blastengine の提供元が開発・保守しているものではありません。コミュニティによって開発された非公式のプラグインです。ご利用は自己責任でお願いいたします。

## 概要

`blastengine_mailer` は、blastengine メールサービスの REST API を使用してメールを送信できる Dify 用ツール・プラグインです。
添付ファイル付きのトランザクション/バルクメールを送信できます。

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/r3-yamauchi/dify-blastengine-mailer-plugin)

## 特長

- **2種類のツール**: `send_transactional_email` (即時送信、CC/BCC対応) と `send_bulk_email` (CSV対応のキャンペーン) のみを提供し、用途を明確化。
- **添付ファイル対応**: メールへの添付ファイル機能を完全サポート（最大10件、合計1MBまで）。
- **直接 REST API 呼び出し**: 公式 blastengine SDK への依存なし。リトライロジックとレート制限ハンドリングを内蔵した HTTP クライアントを使用。
- **添付ガードレール**: 禁止拡張子（.exe/.bat/.js/.vbs/.zip/.gz/.dll/.scr）を事前にブロックし、1通あたり最大10件・合計1MBまでに制限。
- **宛先バリデーション**: トランザクションは最大10件（TO、CC、BCCそれぞれ）、バルクは最大50件＋CSV入力に対応。重複や空行は自動除去。
- **セキュリティ**: デバッグログを適切にサニタイズし、本番環境での機密情報漏洩を防止。
- **資格情報チェック**: `login_id` / `api_key` を Provider 設定時に検証し、初期化エラーを早期発見。

## 前提条件

- プラグイン機能が有効な Dify インスタンス
- blastengine アカウントと API 利用権限
- ログインID (`login_id`) と APIキー (`api_key`)
- 任意: 既定の From アドレス/名前

## プロバイダー設定

| キー | 必須 | 説明 |
| --- | --- | --- |
| `login_id` | ✅ | blastengine 管理画面のログインID。
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

## ライセンス

MIT License
