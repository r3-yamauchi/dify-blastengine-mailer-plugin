# where: blastengine_mailer/provider/provider.py
# what: Validates Blastengine credentials and initializes provider-level settings.
# why: Prevents misconfigured plugins from attempting to send mail with bad credentials.

from __future__ import annotations

import logging
import re
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

logger = logging.getLogger(__name__)

LOGIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._+-@]+$")
API_KEY_MIN_LENGTH = 16


class BlastengineMailerProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate login ID/API key pair supplied from the Dify console."""

        login_id = (credentials.get("login_id") or "").strip()
        api_key = (credentials.get("api_key") or "").strip()

        if not login_id:
            raise ToolProviderCredentialValidationError("BlastengineのログインIDを入力してください")
        if not LOGIN_ID_PATTERN.match(login_id):
            raise ToolProviderCredentialValidationError("ログインIDの形式が正しくありません")

        if not api_key:
            raise ToolProviderCredentialValidationError("APIキーを入力してください")
        if len(api_key) < API_KEY_MIN_LENGTH:
            raise ToolProviderCredentialValidationError("APIキーが短すぎます。管理画面から正しい値をコピーしてください")

        # Validate credentials by testing HTTP client initialization
        # We don't make an actual API call during validation to avoid rate limits
        try:
            from .http_client import BlastengineHttpClient

            # Create HTTP client to verify token generation works
            client = BlastengineHttpClient(
                login_id=login_id,
                api_key=api_key,
                timeout=5,
                max_retries=0
            )

            # Verify bearer token was generated successfully
            if not client._bearer_token:
                raise ToolProviderCredentialValidationError(
                    "認証トークンの生成に失敗しました"
                )

            logger.info("Blastengine credentials passed basic validation checks")

        except ToolProviderCredentialValidationError:
            raise
        except Exception as exc:
            logger.exception("Failed to validate Blastengine credentials")
            # Sanitize exception message to avoid leaking credentials
            exc_str = str(exc)
            # Mask any long alphanumeric strings that might be API keys
            sanitized_exc = re.sub(r'[A-Za-z0-9]{32,}', '***', exc_str)
            raise ToolProviderCredentialValidationError(
                f"認証情報の検証中にエラーが発生しました: {sanitized_exc}"
            ) from exc
