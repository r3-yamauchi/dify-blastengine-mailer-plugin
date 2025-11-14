# where: blastengine_mailer/tools/send_bulk_email.py
# what: Implements the bulk email sending workflow using blastengine's Python SDK.
# why: Allows workflows to orchestrate campaign-style deliveries with attachments and CSV recipients.

from __future__ import annotations

import csv
import logging
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from . import base
from .file_utils import ResolvedFile, cleanup_files, resolve_files
from . import validators

logger = logging.getLogger(__name__)

MAX_BULK_RECIPIENTS = 50


class SendBulkEmailTool(base.BaseblastengineTool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> list[ToolInvokeMessage]:  # noqa: PLR0912, PLR0915
        resolved_attachments: list[ResolvedFile] = []
        resolved_recipient_files: list[ResolvedFile] = []

        try:
            context = self._load_provider_context()
            subject = (tool_parameters.get("subject") or "").strip()
            if not subject:
                raise ValueError("件名(subject)を指定してください")

            text_body = (tool_parameters.get("text_body") or "").strip()
            html_body = (tool_parameters.get("html_body") or "").strip()
            if not text_body and not html_body:
                raise ValueError("text_body または html_body のどちらか一方は必須です")

            from_address = (tool_parameters.get("from_address") or context.default_from_address or "").strip()
            from_name = (tool_parameters.get("from_name") or context.default_from_name or "").strip()
            if not from_address:
                raise ValueError("Fromアドレスを指定するか、プロバイダー設定のデフォルトを登録してください")

            recipients = validators.normalize_email_list(tool_parameters.get("recipients"))

            recipients_file_param = tool_parameters.get("recipients_file")
            if recipients_file_param:
                resolved_recipient_files = resolve_files([recipients_file_param])
                csv_addresses = self._load_csv_addresses(resolved_recipient_files[0].path)
                recipients.extend(csv_addresses)

            recipients = validators.normalize_email_list(recipients)
            validators.validate_recipients(recipients, MAX_BULK_RECIPIENTS)

            schedule_raw = (tool_parameters.get("schedule_at") or "").strip()
            schedule_time = validators.parse_schedule_datetime(schedule_raw) if schedule_raw else None

            attachments_param = tool_parameters.get("attachments") or []
            resolved_attachments = resolve_files(attachments_param) if attachments_param else []
            validators.validate_attachments(resolved_attachments)

            # Create HTTP client and prepare payload
            client = self._create_http_client(context)

            payload: dict[str, Any] = {
                "subject": subject,
                "from": {"email": from_address, "name": from_name or from_address},
            }

            if text_body:
                payload["text_part"] = text_body
            if html_body:
                payload["html_part"] = html_body

            # Create bulk delivery
            delivery_id = client.create_bulk_delivery(payload, resolved_attachments)

            # Update bulk delivery with initial recipients
            client.update_bulk_delivery(delivery_id, payload, recipients)

            # Commit bulk delivery (with or without schedule)
            delivery_id = client.commit_bulk_delivery(delivery_id, schedule_raw if schedule_time else None)

            logger.info(
                "blastengine bulk email queued (delivery_id=%s, recipients=%s)",
                delivery_id,
                len(recipients),
            )

            response_payload = {
                "delivery_id": delivery_id,
                "recipient_count": len(recipients),
                "subject": subject,
                "scheduled": bool(schedule_time),
            }

            result_text = f"blastengineでバルクメールを送信しました (Delivery ID: {delivery_id}, 宛先 {len(recipients)} 件)"
            if schedule_time:
                result_text += f"\n予約時刻: {schedule_raw}"

            return [
                self._create_text_message(result_text),
                self._create_json_message(response_payload),
            ]
        except Exception as exc:  # noqa: BLE001
            return self._handle_error(exc, "blastengineバルクメール送信")
        finally:
            cleanup_files(resolved_attachments)
            cleanup_files(resolved_recipient_files)

    @staticmethod
    def _load_csv_addresses(path: str) -> list[str]:
        try:
            with open(path, newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                addresses: list[str] = []
                for row in reader:
                    if not row:
                        continue
                    cell = row[0].strip()
                    if cell:
                        addresses.append(cell)
                return addresses
        except FileNotFoundError as exc:  # pragma: no cover - validated earlier
            raise ValueError(f"宛先CSVが見つかりません: {path}") from exc
        except Exception as exc:
            raise ValueError(f"宛先CSVを読み取れません: {exc}") from exc
