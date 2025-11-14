# where: blastengine_mailer/tools/validators.py
# what: Validation utilities for payload fields such as recipients and attachments.
# why: Keep tool logic focused on blastengine orchestration.

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .file_utils import ResolvedFile

MAX_ATTACHMENT_COUNT = 10
MAX_TOTAL_ATTACHMENT_BYTES = 1_000_000  # blastengine docs: default total <= 1 MB
DISALLOWED_EXTENSIONS = {".exe", ".bat", ".js", ".vbs", ".zip", ".gz", ".dll", ".scr"}


def normalize_email_list(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        candidates = [raw_value]
    elif isinstance(raw_value, Iterable):
        candidates = list(raw_value)
    else:
        raise ValueError("宛先リストの形式が正しくありません")

    emails: list[str] = []
    for entry in candidates:
        if entry is None:
            continue
        if isinstance(entry, (list, tuple, set)):
            emails.extend(normalize_email_list(entry))
            continue
        text = str(entry).strip()
        if not text:
            continue
        if "," in text or "\n" in text:
            chunked = [segment.strip() for segment in text.replace("\n", ",").split(",")]
            emails.extend([segment for segment in chunked if segment])
        else:
            emails.append(text)
    
    # メールアドレス形式チェック（包括的なバリデーション）
    validated_emails = []
    for email in emails:
        # @が1つだけ含まれていることを確認
        if "@" not in email or email.count("@") != 1:
            raise ValueError(f"不正なメールアドレス形式です: {email}")
        
        # @の前後に文字があることを確認
        local, domain = email.split("@", 1)
        if not local or not domain:
            raise ValueError(f"不正なメールアドレス形式です: {email}")
        
        # ドメイン部分に少なくとも1つの"."が含まれていることを確認（基本的なドメイン形式チェック）
        if "." not in domain:
            raise ValueError(f"不正なメールアドレス形式です（ドメイン部分が不正）: {email}")
        
        # ローカル部分とドメイン部分が空でないことを確認
        if not local.strip() or not domain.strip():
            raise ValueError(f"不正なメールアドレス形式です: {email}")
        
        validated_emails.append(email)
    
    deduped = []
    seen = set()
    for email in validated_emails:
        lowered = email.lower()
        if lowered not in seen:
            deduped.append(email)
            seen.add(lowered)
    return deduped


def validate_recipients(emails: list[str], maximum: int) -> None:
    if not emails:
        raise ValueError("少なくとも1件の宛先を指定してください")
    if len(emails) > maximum:
        raise ValueError(f"宛先は最大{maximum}件までです")


def validate_attachments(files: list[ResolvedFile]) -> None:
    if len(files) > MAX_ATTACHMENT_COUNT:
        raise ValueError(f"添付ファイルは最大{MAX_ATTACHMENT_COUNT}件までです")

    total_bytes = 0
    file_sizes: list[tuple[str, int]] = []  # (ファイル名, サイズ)のリスト
    
    for file in files:
        path = Path(file.path)
        suffix = path.suffix.lower()
        if suffix in DISALLOWED_EXTENSIONS:
            raise ValueError(f"拡張子 {suffix} のファイルはblastengineで禁止されています")
        try:
            size = os.path.getsize(file.path)
            file_sizes.append((path.name, size))
            total_bytes += size
        except OSError as exc:
            raise ValueError(f"添付ファイルのサイズを取得できません: {path}") from exc
    
    # 合計サイズが制限を超えている場合、詳細なエラーメッセージを表示
    if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
        max_size_mb = MAX_TOTAL_ATTACHMENT_BYTES / 1024 / 1024
        total_size_mb = total_bytes / 1024 / 1024
        file_details = []
        for filename, size in file_sizes:
            size_mb = size / 1024 / 1024
            file_details.append(f"  - {filename}: {size_mb:.2f}MB ({size:,} bytes)")
        
        error_msg = (
            f"添付ファイルの合計サイズが制限を超えています。\n"
            f"合計サイズ: {total_size_mb:.2f}MB ({total_bytes:,} bytes)\n"
            f"制限: {max_size_mb:.0f}MB ({MAX_TOTAL_ATTACHMENT_BYTES:,} bytes)\n"
            f"超過: {total_size_mb - max_size_mb:.2f}MB\n"
            f"ファイル一覧:\n" + "\n".join(file_details) + "\n"
            f"ファイルを減らすか、ファイルサイズを小さくしてください。"
        )
        raise ValueError(error_msg)


def parse_schedule_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError("schedule_at にはISO8601形式の日時を指定してください") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if parsed <= now:
        raise ValueError("schedule_at には現在より未来の日時を指定してください")

    return parsed
