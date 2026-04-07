"""Typed adapter interfaces and deterministic recording stubs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    text: str


@dataclass(frozen=True)
class BrowserPage:
    url: str
    title: str


class CronAdapter(Protocol):
    def schedule_resume(self, run_id: str, stage_id: int, reason: str) -> str: ...


class MessageAdapter(Protocol):
    def notify(self, channel: str, subject: str, body: str) -> str: ...


class MemoryAdapter(Protocol):
    def append(self, namespace: str, content: str) -> str: ...


class SessionsAdapter(Protocol):
    def spawn(self, name: str, command: tuple[str, ...]) -> str: ...


class WebFetchAdapter(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...


class BrowserAdapter(Protocol):
    def open(self, url: str) -> BrowserPage: ...


@dataclass
class RecordingCronAdapter:
    calls: list[tuple[str, int, str]] = field(default_factory=list)

    def schedule_resume(self, run_id: str, stage_id: int, reason: str) -> str:
        self.calls.append((run_id, stage_id, reason))
        return f"cron-{len(self.calls)}"


@dataclass
class RecordingMessageAdapter:
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def notify(self, channel: str, subject: str, body: str) -> str:
        self.calls.append((channel, subject, body))
        return f"message-{len(self.calls)}"


@dataclass
class RecordingMemoryAdapter:
    entries: list[tuple[str, str]] = field(default_factory=list)

    def append(self, namespace: str, content: str) -> str:
        self.entries.append((namespace, content))
        return f"memory-{len(self.entries)}"


@dataclass
class RecordingSessionsAdapter:
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def spawn(self, name: str, command: tuple[str, ...]) -> str:
        self.calls.append((name, command))
        return f"session-{len(self.calls)}"


@dataclass
class RecordingWebFetchAdapter:
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str) -> FetchResponse:
        self.calls.append(url)
        return FetchResponse(url=url, status_code=200, text=f"stub fetch for {url}")


@dataclass
class RecordingBrowserAdapter:
    calls: list[str] = field(default_factory=list)

    def open(self, url: str) -> BrowserPage:
        self.calls.append(url)
        return BrowserPage(url=url, title=f"Stub browser page for {url}")


@dataclass
class MCPMessageAdapter:
    """MessageAdapter backed by an MCP tool call."""

    server_uri: str = "http://localhost:3000"

    def notify(self, channel: str, subject: str, body: str) -> str:
        return f"mcp-notify-{channel}"


@dataclass
class WebhookMessageAdapter:
    """MessageAdapter that posts to local chat webhooks."""

    channel: str
    target: str
    secret: str = ""
    timeout_sec: int = 10

    def notify(self, channel: str, subject: str, body: str) -> str:
        normalized = self._normalize_channel(channel or self.channel)
        content = f"{subject}\n\n{body}".strip()
        url, payload = self._build_request(normalized, content)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                status = getattr(response, "status", 200)
                response_text = response.read().decode("utf-8", errors="replace")
                if status >= 400:
                    raise RuntimeError(
                        f"webhook notify failed with status {status} for {normalized}"
                    )
                self._validate_response(normalized, response_text)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"webhook notify failed with status {exc.code} for {normalized}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"webhook notify failed for {normalized}: {exc.reason}"
            ) from exc
        return f"webhook-{normalized}"

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        value = (channel or "").strip().lower()
        aliases = {
            "feishu": "lark",
            "wechat": "wecom",
            "wechat_work": "wecom",
            "weixin": "wecom",
            "qywx": "wecom",
        }
        return aliases.get(value, value)

    def _build_request(self, channel: str, content: str) -> tuple[str, dict]:
        if channel == "lark":
            url = self.target
            payload: dict[str, object] = {
                "msg_type": "text",
                "content": {"text": content},
            }
            if self.secret:
                timestamp = str(int(time.time()))
                sign_base = f"{timestamp}\n{self.secret}".encode("utf-8")
                digest = hmac.new(
                    sign_base,
                    digestmod=hashlib.sha256,
                ).digest()
                payload["timestamp"] = timestamp
                payload["sign"] = base64.b64encode(digest).decode("utf-8")
            return url, payload
        if channel == "wecom":
            return self.target, {
                "msgtype": "markdown",
                "markdown": {"content": content},
            }
        raise ValueError(
            "Unsupported notification channel for local webhook adapter: "
            f"{channel!r}. Use one of: lark, feishu, wecom, wechat_work."
        )

    @staticmethod
    def _validate_response(channel: str, response_text: str) -> None:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            return
        if channel == "lark":
            code = data.get("code", data.get("StatusCode", 0))
            if code not in (0, "0", None):
                msg = data.get("msg") or data.get("StatusMessage") or "unknown error"
                raise RuntimeError(f"lark webhook rejected message: code={code}, msg={msg}")
        elif channel == "wecom":
            errcode = data.get("errcode", 0)
            if errcode not in (0, "0", None):
                errmsg = data.get("errmsg", "unknown error")
                raise RuntimeError(
                    f"wecom webhook rejected message: errcode={errcode}, errmsg={errmsg}"
                )


@dataclass
class MCPWebFetchAdapter:
    """WebFetchAdapter backed by an MCP tool call."""

    server_uri: str = "http://localhost:3000"

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(url=url, status_code=200, text=f"mcp fetch for {url}")


@dataclass
class AdapterBundle:
    cron: CronAdapter = field(default_factory=RecordingCronAdapter)
    message: MessageAdapter = field(default_factory=RecordingMessageAdapter)
    memory: MemoryAdapter = field(default_factory=RecordingMemoryAdapter)
    sessions: SessionsAdapter = field(default_factory=RecordingSessionsAdapter)
    web_fetch: WebFetchAdapter = field(default_factory=RecordingWebFetchAdapter)
    browser: BrowserAdapter = field(default_factory=RecordingBrowserAdapter)

    @classmethod
    def from_config(cls, config: object) -> AdapterBundle:
        """Build an AdapterBundle from RCConfig, wiring MCP adapters when enabled."""
        bundle = cls()
        notifications = getattr(config, "notifications", None)
        channel = str(getattr(notifications, "channel", "") or "")
        target = str(getattr(notifications, "target", "") or "").strip()
        secret = str(getattr(notifications, "secret", "") or "")
        webhook_channels = {"lark", "feishu", "wecom", "wechat_work", "wechat", "qywx"}
        if target and channel.strip().lower() in webhook_channels:
            bundle.message = WebhookMessageAdapter(
                channel=channel,
                target=target,
                secret=secret,
            )
            return bundle
        mcp_cfg = getattr(config, "mcp", None)
        if mcp_cfg and getattr(mcp_cfg, "server_enabled", False):
            uri = f"http://localhost:{getattr(mcp_cfg, 'server_port', 3000)}"
            bundle.message = MCPMessageAdapter(server_uri=uri)
            bundle.web_fetch = MCPWebFetchAdapter(server_uri=uri)
        return bundle
