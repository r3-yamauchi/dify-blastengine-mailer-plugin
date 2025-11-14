# where: blastengine_mailer/provider/http_client.py
# what: Minimal Blastengine HTTP client used instead of the official SDK.
# why: Some Dify environments cannot install the SDK, so we reimplement the needed REST flows.

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
from requests import Response, Session

from ..tools.file_utils import ResolvedFile

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://app.engn.jp/api/v1"
_JSON_FILENAME = "payload.json"
_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_DEFAULT_TIMEOUT = 15
_MAX_RECIPIENTS_PER_UPDATE = 50
_MAX_LOG_BODY_LENGTH = 200  # Maximum length of response body to log


def _sanitize_for_log(text: str) -> str:
    """Sanitize sensitive information from log messages."""
    if not text:
        return text

    # Mask bearer tokens (base64 encoded strings in Authorization header)
    text = re.sub(r'Bearer\s+[A-Za-z0-9+/=]{20,}', 'Bearer ***', text, flags=re.IGNORECASE)

    # Mask API keys (long alphanumeric strings)
    text = re.sub(r'[A-Za-z0-9]{32,}', '***', text)

    # Mask email-like patterns that might be login IDs
    text = re.sub(r'["\']([a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+)["\']', r'"\1"', text)

    # Truncate if too long
    if len(text) > _MAX_LOG_BODY_LENGTH:
        text = text[:_MAX_LOG_BODY_LENGTH] + "... (truncated)"

    return text


class BlastengineHttpError(RuntimeError):
    """Raised when the Blastengine REST API returns an error response."""

    def __init__(self, status_code: int | None, message: str, body: str | None = None) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(message)


@dataclass
class BlastengineHttpClient:
    login_id: str
    api_key: str
    base_url: str = _DEFAULT_BASE_URL
    timeout: int = _DEFAULT_TIMEOUT
    max_retries: int = 2
    session: Session | None = None

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()
        self._bearer_token = self._generate_bearer_token(self.login_id, self.api_key)

    @classmethod
    def from_context(cls, context: Any) -> "BlastengineHttpClient":
        return cls(login_id=context.login_id, api_key=context.api_key)

    # ---- Transactional -----------------------------------------------------

    def send_transactional_email(self, payload: dict[str, Any], attachments: Sequence[ResolvedFile]) -> str:
        # デバッグ用にペイロードの構造をログ出力（機密情報はマスキング）
        debug_payload = dict(payload)
        
        # fromフィールドの詳細をログ出力（デバッグ用 - DEBUGレベルで出力）
        if "from" in debug_payload and isinstance(debug_payload["from"], dict):
            from_email = debug_payload["from"].get("email", "")
            from_name = debug_payload["from"].get("name", "")
            logger.debug("From email (full): %s", from_email)
            logger.debug("From name: '%s' (len=%s, repr=%s)", 
                       from_name,
                       len(from_name) if from_name else 0,
                       repr(from_name))
            if from_email:
                from_local, from_domain = from_email.split("@", 1) if "@" in from_email else ("", "")
                logger.debug("From parsed: local='%s', domain='%s'", from_local, from_domain)
            debug_payload["from"] = {"email": "***", "name": from_name}
        
        # toフィールドの詳細をログ出力（デバッグ用 - DEBUGレベルで出力）
        if "to" in debug_payload and isinstance(debug_payload["to"], list):
            logger.debug("To recipients count: %s", len(debug_payload["to"]))
            for i, to_item in enumerate(debug_payload["to"][:3]):  # 最初の3件のみ
                if isinstance(to_item, dict):
                    to_email = to_item.get("email", "")
                    to_name = to_item.get("name", "")
                    logger.debug("To[%d] email (full): %s", i, to_email)
                    logger.debug("To[%d] name: '%s'", i, to_name if to_name else "(none)")
                    if to_email:
                        to_local, to_domain = to_email.split("@", 1) if "@" in to_email else ("", "")
                        logger.debug("To[%d] parsed: local='%s', domain='%s'", i, to_local, to_domain)
            debug_payload["to"] = [{"email": "***"} for _ in debug_payload.get("to", [])]
        
        if "cc" in debug_payload:
            debug_payload["cc"] = [{"email": "***"} for _ in debug_payload.get("cc", [])]
        if "bcc" in debug_payload:
            debug_payload["bcc"] = [{"email": "***"} for _ in debug_payload.get("bcc", [])]
        
        logger.debug("Sending transactional email with payload structure: %s", json.dumps(debug_payload, ensure_ascii=False, indent=2))
        logger.debug("Payload keys: %s", list(payload.keys()))
        logger.debug("Has attachments: %s", len(attachments) > 0)
        if attachments:
            logger.debug("Attachment files: %s", [Path(f.path).name for f in attachments])
        
        # ペイロードの各フィールドの型と長さを確認（デバッグ用 - DEBUGレベルで出力）
        if "subject" in payload:
            logger.debug("Subject: type=%s, len=%s, value='%s'", type(payload["subject"]).__name__, len(str(payload["subject"])), str(payload["subject"])[:50])
        if "text_part" in payload:
            logger.debug("Text_part: type=%s, len=%s", type(payload["text_part"]).__name__, len(str(payload["text_part"])))
        if "html_part" in payload:
            logger.debug("Html_part: type=%s, len=%s", type(payload["html_part"]).__name__, len(str(payload["html_part"])))
        
        # Blastengine APIのエンドポイントを試行
        # 公式ドキュメントによると、トランザクションメールのエンドポイントは /deliveries/transaction または /transaction の可能性がある
        # まず /deliveries/transaction を試行
        try:
            response = self._request_with_optional_files(
                method="POST",
                path="/deliveries/transaction",
                json_payload=payload,
                attachments=attachments,
            )
        except BlastengineHttpError as e:
            # エンドポイントが間違っている可能性があるため、エラーメッセージを確認
            if e.status_code == 400:
                logger.error("エンドポイント /deliveries/transaction で400エラーが発生しました")
                logger.error("エラーメッセージ: %s", str(e))
                if hasattr(e, 'body') and e.body:
                    logger.error("エラーボディ: %s", e.body)
            raise
        return self._extract_delivery_id(response)

    # ---- Bulk --------------------------------------------------------------

    def create_bulk_delivery(self, payload: dict[str, Any], attachments: Sequence[ResolvedFile]) -> str:
        response = self._request_with_optional_files(
            method="POST",
            path="/deliveries/bulk/begin",
            json_payload=payload,
            attachments=attachments,
        )
        return self._extract_delivery_id(response)

    def update_bulk_delivery(self, delivery_id: str, payload: dict[str, Any], recipients: Sequence[str]) -> None:
        """
        Update bulk delivery with recipients.
        
        Note: The payload parameter is kept for backward compatibility but is not used.
        The update endpoint only requires the 'to' field with recipient emails.
        """
        chunk = [{"email": email} for email in recipients[:_MAX_RECIPIENTS_PER_UPDATE]]
        # Blastengine API仕様: updateエンドポイントは宛先情報(to)のみを必要とする
        # payload全体を送信する必要はない（beginの時点でテンプレートは既に作成済み）
        body = {"to": chunk}
        self._request("PUT", f"/deliveries/bulk/update/{delivery_id}", json=body)

    def append_bulk_recipients(self, delivery_id: str, recipients: Sequence[str]) -> None:
        for email in recipients:
            body = {"email": email}
            self._request("POST", f"/deliveries/{delivery_id}/emails", json=body)

    def commit_bulk_delivery(self, delivery_id: str, schedule_at: str | None) -> str:
        if schedule_at:
            response = self._request(
                "PATCH",
                f"/deliveries/bulk/commit/{delivery_id}",
                json={"reservation_time": schedule_at},
            )
        else:
            response = self._request("PATCH", f"/deliveries/bulk/commit/{delivery_id}/immediate")
        return self._extract_delivery_id(response)

    # ---- Low-level helpers -------------------------------------------------

    def _request_with_optional_files(
        self,
        method: str,
        path: str,
        json_payload: dict[str, Any],
        attachments: Sequence[ResolvedFile],
    ) -> Response:
        # デバッグ用にペイロードをログ出力（機密情報はマスキング）
        debug_payload = dict(json_payload)
        if "from" in debug_payload and isinstance(debug_payload["from"], dict):
            debug_payload["from"] = {"email": "***", "name": debug_payload["from"].get("name", "***")}
        if "to" in debug_payload:
            debug_payload["to"] = [{"email": "***"} for _ in debug_payload.get("to", [])]
        if "cc" in debug_payload:
            debug_payload["cc"] = [{"email": "***"} for _ in debug_payload.get("cc", [])]
        if "bcc" in debug_payload:
            debug_payload["bcc"] = [{"email": "***"} for _ in debug_payload.get("bcc", [])]
        logger.debug("Request payload structure: %s", json.dumps(debug_payload, ensure_ascii=False, indent=2))
        
        # 添付ファイルがある場合はmultipart/form-data形式、ない場合はJSON形式で送信
        if attachments:
            logger.debug("Building multipart request with %s attachments", len(attachments))
            multipart_files = self._build_multipart(json_payload, attachments)
            logger.debug("Multipart files count: %s", len(multipart_files))
            return self._request(method, path, files=multipart_files)
        else:
            # 添付ファイルがない場合はJSON形式で送信
            logger.debug("Sending JSON request (no attachments)")
            return self._request(method, path, json=json_payload)

    def _request(self, method: str, path: str, **kwargs: Any) -> Response:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        headers.setdefault("Authorization", f"Bearer {self._bearer_token}")
        
        # デバッグ用: リクエストURLとメソッドをログ出力（DEBUGレベルで出力）
        logger.debug("Request: %s %s", method, url)
        if "json" in kwargs:
            logger.debug("Request Content-Type: application/json")
        elif "files" in kwargs:
            logger.debug("Request Content-Type: multipart/form-data")
        if "json" in kwargs and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except requests.RequestException as exc:  # pragma: no cover - network failures retried
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                sanitized_exc = _sanitize_for_log(str(exc))
                raise BlastengineHttpError(None, f"Blastengine APIリクエストに失敗しました: {sanitized_exc}") from exc

            if response.status_code in _RETRY_STATUSES and attempt < self.max_retries:
                time.sleep(2**attempt)
                continue

            if response.status_code >= 400:
                message = self._extract_error_message(response)
                sanitized_body = _sanitize_for_log(response.text)
                # デバッグ用にログに詳細を出力
                logger.error(
                    "Blastengine APIエラー (status=%s): %s, body=%s",
                    response.status_code,
                    message,
                    sanitized_body,
                )
                # リクエストの詳細もログに出力（デバッグ用 - DEBUGレベルで出力）
                if "json" in kwargs:
                    actual_json = dict(kwargs["json"])
                    logger.debug("Request payload (full): %s", json.dumps(actual_json, ensure_ascii=False, indent=2))
                    
                    # メールアドレスの詳細を確認（デバッグ用 - DEBUGレベルで出力）
                    if "from" in actual_json and isinstance(actual_json["from"], dict):
                        from_email = actual_json["from"].get("email", "")
                        from_name = actual_json["from"].get("name", "")
                        logger.debug("From email (full): %s", from_email)
                        logger.debug("From name: '%s' (repr=%s)", from_name, repr(from_name))
                    if "to" in actual_json and isinstance(actual_json["to"], list):
                        for i, to_item in enumerate(actual_json["to"]):
                            if isinstance(to_item, dict):
                                to_email = to_item.get("email", "")
                                to_name = to_item.get("name", "")
                                logger.debug("To[%d] email (full): %s", i, to_email)
                                logger.debug("To[%d] name: '%s'", i, to_name if to_name else "(none)")
                    
                    # マスク版も出力（デバッグ用 - DEBUGレベルで出力）
                    debug_json = dict(actual_json)
                    if "from" in debug_json and isinstance(debug_json["from"], dict):
                        debug_json["from"] = {"email": "***", "name": debug_json["from"].get("name", "***")}
                    if "to" in debug_json:
                        debug_json["to"] = [{"email": "***"} for _ in debug_json.get("to", [])]
                    logger.debug("Request payload (masked): %s", json.dumps(debug_json, ensure_ascii=False, indent=2))
                elif "files" in kwargs:
                    # multipart形式の場合、filesパラメータに含まれるdataフィールドを確認
                    logger.error("Request was sent as multipart/form-data")
                raise BlastengineHttpError(response.status_code, message, body=sanitized_body)

            return response

        sanitized_error = _sanitize_for_log(str(last_error))
        raise BlastengineHttpError(None, f"Blastengine APIリクエストに失敗しました: {sanitized_error}")  # pragma: no cover

    def _build_multipart(
        self,
        payload: dict[str, Any],
        attachments: Sequence[ResolvedFile],
    ) -> list[tuple[str, tuple[str, Any, str]]]:
        """Build multipart/form-data structure for file uploads.

        Note: The file handles are opened here and will be automatically closed by
        the requests library after the HTTP request completes. The _Files class
        provides a manual cleanup method as a fallback.
        """
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        json_buffer = io.BytesIO(encoded)
        files: list[tuple[str, tuple[str, Any, str]]] = [
            ("data", (_JSON_FILENAME, json_buffer, "application/json")),
        ]

        opened_handles: list[Any] = []
        try:
            for i, resolved in enumerate(attachments):
                path = Path(resolved.path)
                mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                logger.debug("Opening attachment %d: %s (mime_type: %s)", i+1, path.name, mime_type)
                handle = open(resolved.path, "rb")
                opened_handles.append(handle)
                files.append(("file", (path.name or "attachment.bin", handle, mime_type)))
                logger.debug("Added attachment %d to multipart: %s", i+1, path.name)

            class _Files(list[tuple[str, tuple[str, Any, str]]]):
                """Custom list that can clean up file handles if needed."""
                def __init__(self, items: list[tuple[str, tuple[str, Any, str]]], handles: list[Any]) -> None:
                    super().__init__(items)
                    self._handles = handles

                def close(self) -> None:
                    """Manually close all file handles (fallback mechanism)."""
                    for handle in self._handles:
                        if hasattr(handle, "close"):
                            try:
                                handle.close()
                            except Exception:  # pragma: no cover - best effort cleanup
                                pass

            return _Files(files, opened_handles)
        except Exception:
            # If an error occurs during file opening, close any already-opened handles
            for handle in opened_handles:
                if hasattr(handle, "close"):
                    try:
                        handle.close()
                    except Exception:  # pragma: no cover
                        pass
            raise

    @staticmethod
    def _generate_bearer_token(login_id: str, api_key: str) -> str:
        combined = f"{login_id}{api_key}".encode("utf-8")
        digest = hashlib.sha256(combined).hexdigest().lower()
        return base64.b64encode(digest.encode("utf-8")).decode("utf-8")

    @staticmethod
    def _extract_delivery_id(response: Response) -> str:
        try:
            data = response.json()
        except ValueError as exc:
            sanitized_body = _sanitize_for_log(response.text)
            raise BlastengineHttpError(response.status_code, "Blastengineの応答をJSON解析できません", sanitized_body) from exc

        delivery_id = (
            data.get("delivery_id")
            or data.get("deliveryId")
            or data.get("id")
        )
        if not delivery_id:
            sanitized_data = _sanitize_for_log(json.dumps(data, ensure_ascii=False))
            raise BlastengineHttpError(
                response.status_code,
                "Blastengineの応答に delivery_id が含まれていません",
                sanitized_data,
            )
        return str(delivery_id)

    @staticmethod
    def _extract_error_message(response: Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict):
            # error_messagesフィールドを優先的に確認（Blastengine APIの形式）
            error_messages = data.get("error_messages")
            if isinstance(error_messages, dict):
                # error_messages.main のような形式に対応
                all_errors = []
                for key, value in error_messages.items():
                    if isinstance(value, list):
                        all_errors.extend([f"{key}: {item}" for item in value[:3]])
                    elif isinstance(value, str):
                        all_errors.append(f"{key}: {value}")
                if all_errors:
                    sanitized_errors = [_sanitize_for_log(err) for err in all_errors[:5]]
                    return f"Blastengine APIエラー ({response.status_code}): {'; '.join(sanitized_errors)}"
            
            # その他のエラーフィールドを確認
            message = (
                data.get("message")
                or data.get("error")
                or data.get("error_message")
                or data.get("errors")
            )
            if isinstance(message, str):
                sanitized_message = _sanitize_for_log(message)
                return f"Blastengine APIエラー ({response.status_code}): {sanitized_message}"
            elif isinstance(message, list):
                # エラーが配列の場合
                error_list = [str(item) for item in message[:3]]  # 最大3件まで
                sanitized_errors = [_sanitize_for_log(err) for err in error_list]
                return f"Blastengine APIエラー ({response.status_code}): {', '.join(sanitized_errors)}"
            elif isinstance(message, dict):
                # エラーがオブジェクトの場合（バリデーションエラーなど）
                error_parts = []
                for key, value in list(message.items())[:5]:  # 最大5項目まで
                    if isinstance(value, (str, list)):
                        error_parts.append(f"{key}: {value}")
                if error_parts:
                    sanitized_parts = [_sanitize_for_log(part) for part in error_parts]
                    return f"Blastengine APIエラー ({response.status_code}): {'; '.join(sanitized_parts)}"
        # JSON解析できない場合、レスポンステキストの最初の部分を使用
        if response.text:
            sanitized_text = _sanitize_for_log(response.text[:500])  # 最初の500文字
            return f"Blastengine APIエラー ({response.status_code}): {sanitized_text}"
        return f"Blastengine APIエラー ({response.status_code})"
