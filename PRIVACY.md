# Privacy Policy

## English

### Data Handling
This plugin exchanges the minimum data required to send email through blastengine:
1. **blastengine Credentials** – `login_id` and `api_key` are supplied by users through Dify's secret storage and are only forwarded to the official blastengine SDK during request execution.
2. **Email Payloads** – recipient addresses, subjects, message bodies, headers, metadata, and optional attachments provided as tool inputs are serialized into the blastengine Transaction/Bulk objects.
3. **Delivery Identifiers** – IDs returned by blastengine are surfaced back to the workflow for status tracking.

### Data Storage
- The plugin does not persist credentials, payloads, or attachments on disk. Temporary files supplied by Dify are deleted automatically by the runtime.
- No telemetry or message content is logged beyond minimal delivery identifiers for debugging if logging is enabled.

### Security
- All outbound calls use blastengine's HTTPS endpoints.
- Secrets remain managed by Dify; the plugin only reads them in memory when a tool runs.
- Attachments are validated locally to avoid uploading unsupported formats.

### Third-Party Disclosure
- Data is sent only to blastengine's official API endpoints selected by the user. No other third parties receive any information.

---

## 日本語

### 取り扱うデータ
`blastengine_mailer` はメール送信に必要な最小限の情報のみを扱います。
1. **blastengine認証情報** – `login_id` と `api_key` はDifyのシークレット管理で保存され、ツール実行時にSDKへ渡すときのみ使用します。
2. **メールペイロード** – 受信者、件名、本文、ヘッダー、メタデータ、添付ファイルなどツール入力として受け取った内容を `Transaction` / `Bulk` オブジェクトに変換します。
3. **配信ID** – blastengineから返却されるDelivery IDをワークフローに返し、ステータス確認に利用します。

### データ保存
- プラグインは認証情報やメール内容をローカルディスクに保存しません。Difyが提供する一時ファイルは実行終了後に削除されます。
- ログにはDelivery IDなど最小限のメタデータのみを記録し、本文/添付ファイルの内容は記録しません。

### セキュリティ
- すべての通信はblastengineのHTTPSエンドポイントを使用します。
- シークレットはDify側で管理され、プラグインはツール実行時のみメモリ上で参照します。
- 添付ファイルは送信前にローカル検証し、禁止拡張子やサイズ超過を防ぎます。

### 第三者提供
- ユーザーが指定したblastengine公式API以外の第三者へデータを送信することはありません。
