# where: blastengine_mailer/tools/send_transactional_email.py
# what: Implements the transactional email sending tool via blastengine's Python SDK.
# why: Allow Dify workflows to trigger immediate, attachment-capable notifications.

from __future__ import annotations

import json
import logging
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from . import base
from .file_utils import ResolvedFile, cleanup_files, resolve_files
from . import validators

logger = logging.getLogger(__name__)

MAX_TRANSACTIONAL_RECIPIENTS = 10


class SendTransactionalEmailTool(base.BaseblastengineTool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> list[ToolInvokeMessage]:  # noqa: PLR0912
        resolved_files: list[ResolvedFile] = []
        try:
            context = self._load_provider_context()
            recipients = validators.normalize_email_list(tool_parameters.get("to"))
            logger.debug("Normalized recipients: count=%s, addresses=%s", len(recipients), recipients[:3] if recipients else [])
            validators.validate_recipients(recipients, MAX_TRANSACTIONAL_RECIPIENTS)

            # CCとBCCの処理
            cc_recipients = validators.normalize_email_list(tool_parameters.get("cc"))
            if cc_recipients:
                validators.validate_recipients(cc_recipients, MAX_TRANSACTIONAL_RECIPIENTS)

            bcc_recipients = validators.normalize_email_list(tool_parameters.get("bcc"))
            if bcc_recipients:
                validators.validate_recipients(bcc_recipients, MAX_TRANSACTIONAL_RECIPIENTS)

            subject = (tool_parameters.get("subject") or "").strip()
            if not subject:
                raise ValueError("件名(subject)を指定してください")

            text_body = (tool_parameters.get("text_body") or "").strip()
            html_body = (tool_parameters.get("html_body") or "").strip()
            # blastengine API仕様: text_partは必須フィールド
            # html_partのみの場合は、text_partに空文字列を設定するか、html_partのテキスト版を使用
            if not text_body and not html_body:
                raise ValueError("text_body または html_body のどちらか一方は必須です")
            # text_partが空でhtml_partのみの場合、text_partに最小限のテキストを設定
            if not text_body and html_body:
                # HTMLからテキストを抽出するか、最小限のテキストを設定
                # 簡易的な対応として、空文字列ではなく最小限のテキストを設定
                text_body = "(HTMLメール)"

            from_address = (tool_parameters.get("from_address") or context.default_from_address or "").strip()
            from_name = (tool_parameters.get("from_name") or context.default_from_name or "").strip()
            if not from_address:
                raise ValueError("Fromアドレスを指定するか、プロバイダー設定のデフォルトを登録してください")
            
            # デバッグ用ログ（DEBUGレベルで出力）
            logger.debug("Email parameters: subject=%s, text_body_len=%s, html_body_len=%s, from=%s", 
                       subject[:50] if subject else "", 
                       len(text_body), 
                       len(html_body),
                       from_address[:30] if from_address else "")

            reply_to = (tool_parameters.get("reply_to") or "").strip()
            custom_headers = self._normalize_headers(tool_parameters.get("custom_headers"))
            if reply_to:
                custom_headers.setdefault("Reply-To", reply_to)

            attachments_param = tool_parameters.get("attachments") or []
            resolved_files = resolve_files(attachments_param) if attachments_param else []
            validators.validate_attachments(resolved_files)

            # Create HTTP client and prepare payload
            client = self._create_http_client(context)

            # fromアドレスの形式を確認（validators.normalize_email_list()を使用して検証）
            from_email_list = validators.normalize_email_list([from_address])
            if not from_email_list:
                raise ValueError(f"Fromアドレスが不正なメールアドレス形式です: {from_address}")
            # 検証済みのfrom_addressを使用
            validated_from_address = from_email_list[0]
            if validated_from_address != from_address:
                # 正規化されたアドレスを使用（大文字小文字の違いなど）
                from_address = validated_from_address
            logger.debug("From address validated: %s", from_address[:10] + "***" if len(from_address) > 10 else "***")
            
            # fromフィールドの構築（nameが空の場合は省略）
            from_field: dict[str, str] = {"email": from_address}
            if from_name and from_name.strip():
                from_field["name"] = from_name.strip()
            elif not from_name:
                # from_nameが指定されていない場合は、emailアドレスをnameとして使用
                from_field["name"] = from_address
            
            # 宛先リストが空でないことを確認（validators.normalize_email_list()で既に検証済み）
            if not recipients:
                raise ValueError("宛先(to)が空です。少なくとも1件のメールアドレスを指定してください")
            
            # blastengine API仕様: toフィールドは文字列形式（単一のメールアドレス）
            # 複数の宛先がある場合、最初の宛先をtoに設定し、残りはccに追加
            
            # 最初の宛先をtoフィールドに設定（文字列形式）
            to_email = recipients[0]
            logger.debug("To email (string): %s", to_email)
            
            # 複数の宛先がある場合、2件目以降をccに追加
            additional_recipients = recipients[1:]
            if additional_recipients:
                logger.debug("Additional recipients will be added to CC: %s", additional_recipients)
                # 既存のcc_recipientsに追加
                if not cc_recipients:
                    cc_recipients = []
                cc_recipients = list(cc_recipients) + additional_recipients
            
            payload: dict[str, Any] = {
                "subject": subject,
                "from": from_field,
                "to": to_email,  # 文字列形式で指定
                "encode": "UTF-8",  # blastengine API仕様: encodeフィールドを追加
            }
            
            # ペイロードの最終確認（デバッグ用 - DEBUGレベルで出力）
            logger.debug("Payload constructed - keys: %s", list(payload.keys()))
            logger.debug("Payload 'to' field type: %s, value: %s", type(payload["to"]), payload["to"])

            # blastengine API仕様: ccとbccは配列形式（文字列の配列）
            if cc_recipients:
                payload["cc"] = cc_recipients  # 文字列の配列

            if bcc_recipients:
                payload["bcc"] = bcc_recipients  # 文字列の配列

            # blastengine API仕様: text_partは必須フィールド
            # 空文字列でないことを確認
            if not text_body or not text_body.strip():
                raise ValueError("text_partは必須フィールドです。text_bodyを指定してください")
            payload["text_part"] = text_body
            
            # html_partはオプション
            if html_body:
                payload["html_part"] = html_body

            # custom_headersが空でない場合のみ追加
            if custom_headers and len(custom_headers) > 0:
                payload["custom_headers"] = custom_headers

            # Send email via HTTP client
            delivery_id = client.send_transactional_email(payload, resolved_files)
            total_recipients = len(recipients) + len(cc_recipients) + len(bcc_recipients)
            logger.info(
                "blastengine transactional email queued (delivery_id=%s, to=%s, cc=%s, bcc=%s, total=%s)",
                delivery_id,
                len(recipients),
                len(cc_recipients),
                len(bcc_recipients),
                total_recipients,
            )

            response = {
                "delivery_id": delivery_id,
                "recipients": recipients,
                "subject": subject,
                "attachments": [file.path for file in resolved_files],
            }

            if cc_recipients:
                response["cc"] = cc_recipients
            if bcc_recipients:
                response["bcc"] = bcc_recipients

            result_text = f"blastengineでトランザクションメールを送信しました (Delivery ID: {delivery_id})"
            return [
                self._create_text_message(result_text),
                self._create_json_message(response),
            ]
        except Exception as exc:  # noqa: BLE001
            return self._handle_error(exc, "blastengineトランザクションメール送信")
        finally:
            cleanup_files(resolved_files)

    @staticmethod
    def _normalize_headers(raw_value: Any) -> dict[str, str]:
        if not raw_value:
            return {}
        if isinstance(raw_value, dict):
            source = raw_value
        elif hasattr(raw_value, "model_dump"):
            source = raw_value.model_dump()
        elif isinstance(raw_value, str):
            try:
                source = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ValueError("custom_headers は JSON オブジェクト形式で指定してください") from exc
        else:
            raise ValueError("custom_headers の形式が無効です")

        normalized: dict[str, str] = {}
        for key, value in source.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if not isinstance(value, str):
                value = str(value)
            normalized[key.strip()] = value.strip()
        return normalized
