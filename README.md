# blastengine_mailer

**Author:** r3-yamauchi  
**Version:** 0.0.1  
**Type:** tool

English | [Japanese](https://github.com/r3-yamauchi/dify-blastengine-mailer-plugin/blob/main/readme/README_ja_JP.md)

> ⚠️ **Note: This is an unofficial plugin**  
> This plugin is not developed or maintained by blastengine's official provider. It is a community-developed plugin created by independent developers. Use at your own discretion.

## Description

`blastengine_mailer` provides direct REST API integration with blastengine email service for Dify workflows. Send transactional alerts or bulk campaigns with attachments without requiring the official Python SDK. This implementation uses the `requests` library to call blastengine APIs directly, making it compatible with restricted Dify environments.

The source code of this plugin is available in the [GitHub repository](https://github.com/r3-yamauchi/dify-blastengine-mailer-plugin).

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/r3-yamauchi/dify-blastengine-mailer-plugin)

## Highlights

- **Two focused tools**: `send_transactional_email` for instant notifications with CC/BCC support, and `send_bulk_email` for campaigns that can read recipients from CSV and optionally schedule future delivery.
- **Attachment support**: Full support for email attachments (up to 10 files, total ≤1 MB) with validation and security checks.
- **Attachment guardrails**: rejects disallowed extensions (`.exe`, `.bat`, `.js`, `.vbs`, `.zip`, `.gz`, `.dll`, `.scr`), enforces ≤10 files, and ensures the aggregated size stays under blastengine's default 1 MB cap.
- **Credential safety**: `login_id` + `api_key` are validated up front, and every tool inherits the same initialization logic.
- **Direct REST API**: No dependency on the official blastengine SDK. Uses HTTP client with built-in retry logic and rate-limit handling.
- **Security**: Debug logs are properly sanitized to prevent sensitive information leakage in production environments.
- **Test scaffolding**: pytest suites stub HTTP requests to verify mapping logic without hitting the real API.

## Provider Setup

1. Upload/package the plugin in Dify.
2. Configure credentials:
   - `login_id` *(secret, required)* – blastengine console login.
   - `api_key` *(secret, required)* – API key paired with the login.
   - `default_from_address` *(optional)* – fallback From address.
   - `default_from_name` *(optional)* – fallback display name.
3. Drop the tools into your workflow nodes and map parameters.

## Tools

### `send_transactional_email`
- Inputs: recipients array (≤10 for TO, CC, BCC each), subject, text and/or HTML body, optional from/reply-to overrides, custom headers, CC/BCC recipients, and up to 10 attachments.
- Outputs: `delivery_id`, recipient echo (including CC/BCC), attachment summary, human-readable status.

### `send_bulk_email`
- Inputs: subject, text/HTML body, recipients (array and/or CSV upload with ≤50 addresses per call), optional schedule timestamp (ISO8601 future time), and attachments.
- Flow: configure template → `bulk.begin()` → add recipients → `bulk.update()` → `bulk.send([schedule_at])`.
- Outputs: `delivery_id`, processed recipient count, schedule flag.

## Attachment & Recipient Rules

- Attachments: ≤10 files, total size ≤1 MB per message, restricted extensions blocked before the API call.
- Recipients: transactional tools allow up to 10 addresses per invocation (TO, CC, BCC each); bulk tools cap at 50 addresses per call and support CSV uploads.

## License

MIT License — full text in `LICENSE`.
