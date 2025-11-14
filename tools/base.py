# where: blastengine_mailer/tools/base.py
# what: Shared helper utilities for blastengine tools (credentials, messaging, validation hooks).
# why: Avoid duplicated logic across transactional/bulk/status tool implementations.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .http_client import blastengineHttpClient

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProviderContext:
    login_id: str
    api_key: str
    default_from_address: str | None = None
    default_from_name: str | None = None


class BaseblastengineTool(Tool):
    """Base class that takes care of credential loading and HTTP client creation."""

    def _load_provider_context(self) -> ProviderContext:
        credentials: dict[str, Any] = getattr(self.runtime, "credentials", {}) or {}
        login_id = (credentials.get("login_id") or "").strip()
        api_key = (credentials.get("api_key") or "").strip()
        default_from_address = (credentials.get("default_from_address") or "").strip() or None
        default_from_name = (credentials.get("default_from_name") or "").strip() or None

        if not login_id or not api_key:
            raise ValueError("blastengineのログインIDとAPIキーを設定してください")

        return ProviderContext(
            login_id=login_id,
            api_key=api_key,
            default_from_address=default_from_address,
            default_from_name=default_from_name,
        )

    def _create_http_client(self, context: ProviderContext) -> blastengineHttpClient:
        """Create a blastengine HTTP client from the provider context."""
        logger.info("Creating blastengine HTTP client for login_id=%s", context.login_id)
        return blastengineHttpClient.from_context(context)

    # ---- Messaging helpers -------------------------------------------------

    def _create_text_message(self, text: str) -> ToolInvokeMessage:
        return self.create_text_message(text)

    def _create_json_message(self, payload: dict[str, Any]) -> ToolInvokeMessage:
        return self.create_json_message(payload)

    def _handle_error(self, error: Exception, action: str) -> list[ToolInvokeMessage]:
        logger.exception("Failed to %s: %s", action, error)
        hints: list[str] = []
        message = str(error)
        lowered = message.lower()
        
        # blastengineHttpErrorの場合は詳細情報を取得
        if isinstance(error, Exception) and hasattr(error, "body") and error.body:
            # エラーボディに詳細情報が含まれている場合
            body_str = str(error.body)
            if body_str and len(body_str) > 0:
                message += f"\n詳細: {body_str[:500]}"  # 最初の500文字まで
        
        if "authentication" in lowered or "api key" in lowered or "401" in message or "403" in message:
            hints.append("blastengineのログインID/APIキーを再確認してください")
        if "rate" in lowered or "429" in lowered:
            hints.append("短時間にリクエストしすぎている可能性があります。数秒待って再実行してください")
        if "attachment" in lowered:
            hints.append("添付ファイルの拡張子・サイズ・個数制限を確認してください")
        if "400" in message or "validation" in lowered or "invalid" in lowered:
            hints.append("リクエストパラメータの形式を確認してください（件名、本文、宛先など）")

        text = f"{action} に失敗しました: {message}"
        if hints:
            text += "\n\n" + "\n".join(f"ヒント: {hint}" for hint in hints)

        return [self._create_text_message(text)]
