"""ACP (Agent Client Protocol) LLM client via acpx.

Uses acpx as the ACP bridge to communicate with any ACP-compatible agent
(Claude Code, Codex, Gemini CLI, etc.) via persistent named sessions.

Key advantage: a single persistent session maintains context across all
23 pipeline stages — the agent remembers everything.
"""

from __future__ import annotations

import atexit
import glob
import http.client
import json
import logging
import os
import re
import socket
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import weakref
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from researchclaw.llm.client import LLMResponse

logger = logging.getLogger(__name__)

# acpx output markers
_DONE_RE = re.compile(r"^\[done\]")
_CLIENT_RE = re.compile(r"^\[client\]")
_ACPX_RE = re.compile(r"^\[acpx\]")
_TOOL_RE = re.compile(r"^\[tool\]")


@dataclass
class ACPConfig:
    """Configuration for ACP agent connection."""

    agent: str = "claude"
    cwd: str = "."
    acpx_command: str = ""  # auto-detect if empty
    session_name: str = "researchclaw"
    timeout_sec: int = 1800  # per-prompt timeout
    gateway_timeout_sec: int = 900  # OpenClaw HTTP gateway timeout


def _find_acpx() -> str | None:
    """Find the acpx binary — check PATH, then OpenClaw's plugin directory."""
    found = shutil.which("acpx")
    if found:
        return found
    # Check OpenClaw's bundled acpx plugin
    openclaw_acpx = os.path.expanduser(
        "~/.openclaw/extensions/acpx/node_modules/.bin/acpx"
    )
    if os.path.isfile(openclaw_acpx) and os.access(openclaw_acpx, os.X_OK):
        return openclaw_acpx
    return None


def _resolve_agent_binary(agent: str) -> str | None:
    """Resolve CLI agent binaries from PATH plus stable local install locations."""
    direct = shutil.which(agent)
    if direct:
        return direct

    candidates: list[str] = []
    env_key = f"RESEARCHCLAW_{agent.upper()}_BINARY"
    env_override = os.environ.get(env_key) or os.environ.get(f"{agent.upper()}_BINARY")
    if env_override:
        candidates.append(os.path.expanduser(env_override))

    if agent == "codex":
        candidates.extend(
            [
                os.path.expanduser("~/.local/bin/codex"),
                os.path.expanduser("~/.codex/bin/codex"),
            ]
        )
        candidates.extend(
            sorted(
                glob.glob(
                    os.path.expanduser(
                        "~/.vscode-server/extensions/openai.chatgpt-*/bin/linux-x86_64/codex"
                    )
                ),
                reverse=True,
            )
        )
    elif agent == "claude":
        candidates.extend(
            [
                os.path.expanduser("~/.local/bin/claude"),
                os.path.expanduser("~/.claude/local/claude"),
            ]
        )

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class ACPClient:
    """LLM client that uses acpx to communicate with ACP agents.

    Spawns persistent named sessions via acpx, reusing them across
    ``.chat()`` calls so the agent maintains context across the full
    23-stage pipeline.
    """

    # Track live instances for atexit cleanup (weak refs to avoid preventing GC)
    _live_instances: list[weakref.ref[ACPClient]] = []
    _atexit_registered: bool = False

    def __init__(self, acp_config: ACPConfig) -> None:
        self.config = acp_config
        self._acpx: str | None = acp_config.acpx_command or None
        self._session_ready = False
        self._named_sessions_usable: bool | None = None
        self._prefer_openclaw_gateway = self._should_prefer_gateway_by_default()
        # Prune dead weakrefs, then track this instance
        ACPClient._live_instances = [r for r in ACPClient._live_instances if r() is not None]
        ACPClient._live_instances.append(weakref.ref(self))
        if not ACPClient._atexit_registered:
            atexit.register(ACPClient._atexit_cleanup)
            ACPClient._atexit_registered = True

    @classmethod
    def from_rc_config(cls, rc_config: Any) -> ACPClient:
        """Build from a ResearchClaw ``RCConfig``."""
        acp = rc_config.llm.acp
        return cls(ACPConfig(
            agent=acp.agent,
            cwd=acp.cwd,
            acpx_command=getattr(acp, "acpx_command", ""),
            session_name=getattr(acp, "session_name", "researchclaw"),
            timeout_sec=getattr(acp, "timeout_sec", 1800),
            gateway_timeout_sec=getattr(acp, "gateway_timeout_sec", 900),
        ))

    # ------------------------------------------------------------------
    # Public interface (matches LLMClient)
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
        system: str | None = None,
        strip_thinking: bool = False,
    ) -> LLMResponse:
        """Send a prompt and return the agent's response.

        Parameters mirror ``LLMClient.chat()`` for drop-in compatibility.
        ``model``, ``max_tokens``, ``temperature``, and ``json_mode`` are
        accepted but not forwarded — the agent manages its own model and
        parameters.
        """
        prompt_text = self._messages_to_prompt(messages, system=system)
        content = self._send_prompt(prompt_text)
        if strip_thinking:
            from researchclaw.utils.thinking_tags import strip_thinking_tags
            content = strip_thinking_tags(content)
        return LLMResponse(
            content=content,
            model=f"acp:{self.config.agent}",
            finish_reason="stop",
        )

    def preflight(self) -> tuple[bool, str]:
        """Check that acpx and the agent are available.

        Keep this lightweight and non-blocking. Runtime prompt sending has
        its own fallback logic when persistent sessions are unavailable.
        """
        acpx = self._resolve_acpx()
        if not acpx:
            return False, (
                "acpx not found. Install it: npm install -g acpx  "
                "or set llm.acp.acpx_command in config."
            )
        # Check the agent binary exists
        agent = self.config.agent
        resolved_agent = _resolve_agent_binary(agent)
        if not resolved_agent:
            return False, f"ACP agent CLI not found: {agent!r} (not on PATH)"
        if self._prefer_openclaw_gateway:
            return True, (
                f"OK - ACP bridge ready ({agent} via acpx, binary={resolved_agent}; "
                "OpenClaw gateway session backend available)"
            )
        return True, f"OK - ACP bridge ready ({agent} via acpx, binary={resolved_agent})"

    def describe_backend_health(self) -> dict[str, Any]:
        """Summarize backend availability and the active fallback chain."""
        gateway_config = self._load_openclaw_gateway_config()
        gateway_url = gateway_config[0] if gateway_config else ""
        gateway_healthy = self._probe_gateway_socket(gateway_url) if gateway_url else False
        if gateway_healthy:
            self._prefer_openclaw_gateway = True
        acpx = self._resolve_acpx()
        agent_binary = _resolve_agent_binary(self.config.agent)

        backend_order: list[str] = []
        if gateway_config:
            backend_order.append("openclaw_gateway")
        if acpx:
            backend_order.extend(["acp_named_session", "acp_exec"])
        if self.config.agent == "codex":
            backend_order.append("codex_exec")
        backend_order.append("diagnostic_fail")

        selected_backend = "diagnostic_fail"
        if self._prefer_openclaw_gateway and gateway_healthy:
            selected_backend = "openclaw_gateway"
        elif acpx and self._named_sessions_usable is not False:
            selected_backend = "acp_named_session"
        elif acpx:
            selected_backend = "acp_exec"
        elif self.config.agent == "codex" and agent_binary:
            selected_backend = "codex_exec"
        elif gateway_healthy:
            selected_backend = "openclaw_gateway"

        return {
            "agent": self.config.agent,
            "session_name": self.config.session_name,
            "cwd": self._abs_cwd(),
            "backend_order": backend_order,
            "selected_backend": selected_backend,
            "prefer_openclaw_gateway": bool(self._prefer_openclaw_gateway),
            "gateway_available": bool(gateway_config),
            "gateway_url": gateway_url,
            "gateway_healthy": gateway_healthy,
            "acpx_available": bool(acpx),
            "agent_binary_available": bool(agent_binary),
            "named_sessions_usable": self._named_sessions_usable,
            "session_ready": bool(self._session_ready),
            "degraded": bool(backend_order and selected_backend != backend_order[0]),
        }

    def close(self) -> None:
        """Close the acpx session."""
        if not self._session_ready or self._named_sessions_usable is False:
            return
        acpx = self._resolve_acpx()
        if not acpx:
            return
        try:
            subprocess.run(
                [acpx, "--ttl", "0", "--cwd", self._abs_cwd(),
                 self.config.agent, "sessions", "close",
                 self.config.session_name],
                capture_output=True, timeout=15,
            )
        except Exception:  # noqa: BLE001
            pass
        self._session_ready = False

    def __del__(self) -> None:
        """Best-effort cleanup on garbage collection."""
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def _atexit_cleanup(cls) -> None:
        """Close all live ACP sessions on interpreter shutdown."""
        for ref in cls._live_instances:
            inst = ref()
            if inst is not None:
                try:
                    inst.close()
                except Exception:  # noqa: BLE001
                    pass
        cls._live_instances.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_acpx(self) -> str | None:
        """Resolve the acpx binary path (cached)."""
        if self._acpx:
            return self._acpx
        self._acpx = _find_acpx()
        return self._acpx

    def _abs_cwd(self) -> str:
        return os.path.abspath(self.config.cwd)

    def _ensure_session(self) -> None:
        """Find or create the named acpx session."""
        if self._session_ready:
            return
        if self._named_sessions_usable is False:
            raise RuntimeError(
                f"No acpx session found (searched up to {self._abs_cwd()}). "
                f"Create one: acpx {self.config.agent} sessions new --name {self.config.session_name}"
            )
        acpx = self._resolve_acpx()
        if not acpx:
            raise RuntimeError("acpx not found")

        # Use 'ensure' which finds existing or creates new
        ensure_cmd = [
            acpx, "--ttl", "0", "--cwd", self._abs_cwd(),
            self.config.agent, "sessions", "ensure",
            "--name", self.config.session_name,
        ]
        try:
            result = subprocess.run(
                ensure_cmd,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            self._named_sessions_usable = False
            self._session_ready = False
            logger.warning(
                "ACP named session ensure timed out after %ss for agent=%s cwd=%s session=%s. "
                "Falling back to one-shot exec.",
                exc.timeout,
                self.config.agent,
                self._abs_cwd(),
                self.config.session_name,
            )
            raise RuntimeError(
                f"No acpx session found (searched up to {self._abs_cwd()}). "
                f"Named session ensure timed out after {int(exc.timeout or 30)}s."
            ) from exc
        if result.returncode != 0:
            # Fall back to 'new'
            new_cmd = [
                acpx, "--ttl", "0", "--cwd", self._abs_cwd(),
                self.config.agent, "sessions", "new",
                "--name", self.config.session_name,
            ]
            try:
                result = subprocess.run(
                    new_cmd,
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=30,
                )
            except subprocess.TimeoutExpired as exc:
                self._named_sessions_usable = False
                self._session_ready = False
                logger.warning(
                    "ACP named session new timed out after %ss for agent=%s cwd=%s session=%s. "
                    "Falling back to one-shot exec.",
                    exc.timeout,
                    self.config.agent,
                    self._abs_cwd(),
                    self.config.session_name,
                )
                raise RuntimeError(
                    f"No acpx session found (searched up to {self._abs_cwd()}). "
                    f"Named session creation timed out after {int(exc.timeout or 30)}s."
                ) from exc
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to create ACP session: {result.stderr.strip()}"
                )
        if not self._session_exists(acpx):
            self._named_sessions_usable = False
            self._session_ready = False
            logger.warning(
                "ACP session command returned success but no session materialized "
                "for agent=%s cwd=%s session=%s. Falling back to one-shot exec.",
                self.config.agent,
                self._abs_cwd(),
                self.config.session_name,
            )
            raise RuntimeError(
                f"No acpx session found (searched up to {self._abs_cwd()}). "
                f"Create one: acpx {self.config.agent} sessions new --name {self.config.session_name}"
            )
        self._named_sessions_usable = True
        self._session_ready = True
        logger.info("ACP session '%s' ready (%s)", self.config.session_name, self.config.agent)

    def _session_exists(self, acpx: str) -> bool:
        """Return True when acpx can resolve the configured named session."""
        try:
            result = subprocess.run(
                [acpx, "--ttl", "0", "--cwd", self._abs_cwd(),
                 self.config.agent, "sessions", "show",
                 self.config.session_name],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=15,
            )
        except Exception:  # noqa: BLE001
            return False

        output = "\n".join(
            part for part in ((result.stdout or "").strip(), (result.stderr or "").strip())
            if part
        ).strip()
        if not output:
            return False
        lowered = output.lower()
        if "no named session" in lowered or "no cwd session" in lowered or "no sessions" in lowered:
            return False
        return result.returncode == 0

    # Linux MAX_ARG_STRLEN is 128 KB; Windows CreateProcess limit is ~32 KB
    # for the entire command line, not just the prompt payload. acpx adds
    # several fixed arguments plus quoting overhead, so leave generous headroom
    # on Windows and switch to temp-file transport earlier.
    _MAX_CLI_PROMPT_BYTES = 20_000 if sys.platform == "win32" else 100_000
    # On Windows, npm-installed CLIs usually resolve to ``.cmd`` launchers,
    # which are routed through ``cmd.exe`` and hit a much smaller practical
    # command-line limit (~8 KB). Use file transport much earlier there.
    _MAX_CMD_WRAPPER_PROMPT_BYTES = 6_000 if sys.platform == "win32" else 100_000

    # Localized error snippets for "command line too long" (may be in any OS language)
    _CMD_TOO_LONG_HINTS = (
        "too long",       # English Windows
        "trop long",      # French Windows
        "zu lang",        # German Windows
        "demasiado larg", # Spanish Windows
        "e2big",          # POSIX
    )

    # Error patterns that indicate a dead/stale session (retryable)
    _RECONNECT_ERRORS = (
        "agent needs reconnect",
        "session not found",
        "Query closed",
    )
    _NO_SESSION_HINTS = (
        "No acpx session found",
        "no acpx session found",
    )
    _OPENCLAW_GATEWAY_HINTS = (
        "GLIBC_2.",
        "libssl.so.3",
        "libcrypto.so.3",
        "codex-acp",
    )
    _MAX_RECONNECT_ATTEMPTS = 2

    @classmethod
    def _cli_prompt_limit(cls, acpx: str | None) -> int:
        """Return the safe inline-prompt size for the resolved ACP launcher."""
        limit = cls._MAX_CLI_PROMPT_BYTES
        if sys.platform == "win32" and acpx:
            lower = acpx.lower()
            if lower.endswith((".cmd", ".bat")):
                return min(limit, cls._MAX_CMD_WRAPPER_PROMPT_BYTES)
        return limit

    def _send_prompt(self, prompt: str) -> str:
        """Send a prompt via acpx and return the response text.

        For large prompts that would exceed the OS argument-length limit
        (``E2BIG``), the prompt is written to a temp file and the agent
        is asked to read it.

        If the session has died (common after long-running stages), retries
        up to ``_MAX_RECONNECT_ATTEMPTS`` times with automatic reconnection.
        """
        acpx = self._resolve_acpx()
        if not acpx:
            raise RuntimeError("acpx not found")
        if self._prefer_openclaw_gateway:
            try:
                return self._send_prompt_via_openclaw_gateway(prompt)
            except RuntimeError as exc:
                logger.warning(
                    "OpenClaw gateway primary session backend failed; falling back to acpx/direct exec: %s",
                    exc,
                )

        prompt_bytes = len(prompt.encode("utf-8"))
        prompt_limit = self._cli_prompt_limit(acpx)
        use_file = prompt_bytes > prompt_limit
        if use_file:
            logger.info(
                "Prompt too large for CLI arg (%d bytes > %d). Using temp file.",
                prompt_bytes,
                prompt_limit,
            )

        last_exc: RuntimeError | None = None
        for attempt in range(1 + self._MAX_RECONNECT_ATTEMPTS):
            try:
                self._ensure_session()
                if use_file:
                    return self._send_prompt_via_file(acpx, prompt)
                return self._send_prompt_cli(acpx, prompt)
            except OSError as os_exc:
                # OS-level failure (e.g., Windows CreateProcess arg limit).
                # Fall back to temp-file transport automatically.
                if not use_file:
                    logger.warning(
                        "CLI subprocess raised OSError, "
                        "falling back to temp file: %s",
                        os_exc,
                    )
                    use_file = True
                    return self._send_prompt_via_file(acpx, prompt)
                raise RuntimeError(
                    f"ACP prompt failed: {os_exc}"
                ) from os_exc
            except RuntimeError as exc:
                # Detect localized "command line too long" from subprocess stderr
                exc_lower = str(exc).lower()
                if not use_file and any(
                    h in exc_lower for h in self._CMD_TOO_LONG_HINTS
                ):
                    logger.warning(
                        "CLI prompt too long for OS, "
                        "falling back to temp file: %s",
                        exc,
                    )
                    use_file = True
                    return self._send_prompt_via_file(acpx, prompt)
                if any(hint in str(exc) for hint in self._NO_SESSION_HINTS):
                    logger.warning(
                        "ACP named session unavailable; falling back to one-shot exec: %s",
                        exc,
                    )
                    return self._fallback_exec_then_gateway(
                        acpx,
                        prompt,
                        primary_error=exc,
                        gateway_log_prefix="ACP named session unavailable",
                    )
                if self._should_use_openclaw_gateway(exc):
                    logger.warning(
                        "ACP session runtime unavailable; falling back to direct exec before gateway: %s",
                        exc,
                    )
                    return self._fallback_exec_then_gateway(
                        acpx,
                        prompt,
                        primary_error=exc,
                        gateway_log_prefix="ACP runtime unavailable",
                    )
                if not any(pat in str(exc) for pat in self._RECONNECT_ERRORS):
                    raise
                last_exc = exc
                if attempt < self._MAX_RECONNECT_ATTEMPTS:
                    logger.warning(
                        "ACP session died (%s), reconnecting (attempt %d/%d)...",
                        exc,
                        attempt + 1,
                        self._MAX_RECONNECT_ATTEMPTS,
                    )
                    self._force_reconnect()

        raise last_exc  # type: ignore[misc]

    def _should_prefer_gateway_by_default(self) -> bool:
        """Prefer OpenClaw's stable HTTP session backend for codex when available."""
        if self.config.agent not in {"codex", "openclaw"}:
            return False
        return self._load_openclaw_gateway_config() is not None

    def _force_reconnect(self) -> None:
        """Close the stale session and reset so _ensure_session creates a new one."""
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass
        self._session_ready = False

    def _send_prompt_cli(self, acpx: str, prompt: str) -> str:
        """Send prompt as a CLI argument (original path)."""
        try:
            result = subprocess.run(
                [acpx, "--approve-all", "--ttl", "0", "--cwd", self._abs_cwd(),
                 self.config.agent, "-s", self.config.session_name,
                 prompt],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.config.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"ACP prompt timed out after {self.config.timeout_sec}s"
            ) from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"ACP prompt failed (exit {result.returncode}): {stderr}")

        return self._extract_response(result.stdout)

    def _send_prompt_exec(self, acpx: str, prompt: str) -> str:
        """Fallback path: use one-shot exec without a persistent ACP session."""
        if self.config.agent == "codex":
            return self._send_prompt_via_codex_exec(prompt)

        try:
            result = subprocess.run(
                [acpx, "--approve-all", "--ttl", "0", "--cwd", self._abs_cwd(),
                 self.config.agent, "exec", prompt],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.config.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"ACP exec prompt timed out after {self.config.timeout_sec}s"
            ) from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"ACP exec failed (exit {result.returncode}): {stderr}")

        return self._extract_response(result.stdout)

    def _fallback_exec_then_gateway(
        self,
        acpx: str,
        prompt: str,
        *,
        primary_error: Exception,
        gateway_log_prefix: str,
    ) -> str:
        """Prefer direct exec; only use OpenClaw gateway as a last resort."""
        try:
            return self._send_prompt_exec(acpx, prompt)
        except RuntimeError as exec_exc:
            if self._is_gateway_timeout_error(primary_error):
                raise RuntimeError(
                    f"{gateway_log_prefix}; gateway timed out and direct exec failed: {exec_exc}"
                ) from exec_exc
            if self._should_use_openclaw_gateway(primary_error) or self._should_use_openclaw_gateway(exec_exc):
                self._prefer_openclaw_gateway = True
                logger.warning(
                    "%s; direct exec failed, using OpenClaw gateway fallback: %s",
                    gateway_log_prefix,
                    exec_exc,
                )
                return self._send_prompt_via_openclaw_gateway(prompt)
            raise

    def _send_prompt_via_codex_exec(self, prompt: str) -> str:
        """Use Codex CLI directly when ACP session orchestration is unavailable."""
        binary = _resolve_agent_binary("codex")
        if not binary:
            raise RuntimeError("codex binary not found on PATH or known local install paths")
        try:
            result = subprocess.run(
                [binary, "exec", "-C", self._abs_cwd()],
                input=prompt,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.config.timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Codex exec prompt timed out after {self.config.timeout_sec}s"
            ) from exc

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"Codex exec failed (exit {result.returncode}): {stderr}")

        return (result.stdout or "").strip()

    def _should_use_openclaw_gateway(self, exc: Exception) -> bool:
        """Return True when the local OpenClaw gateway is a better ACP backend."""
        if self.config.agent not in {"codex", "openclaw"}:
            return False
        message = str(exc)
        if not any(hint in message for hint in self._OPENCLAW_GATEWAY_HINTS):
            return False
        return self._load_openclaw_gateway_config() is not None

    def _load_openclaw_gateway_config(self) -> tuple[str, str, str] | None:
        """Resolve local OpenClaw gateway URL, token, and stable session user."""
        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            return None

        gateway = data.get("gateway") or {}
        auth = gateway.get("auth") or {}
        token = auth.get("token")
        if not token:
            return None

        port = gateway.get("port", 18789)
        bind = gateway.get("bind", "loopback")
        host = "127.0.0.1" if bind == "loopback" else "localhost"
        url = f"http://{host}:{port}/v1/responses"

        # OpenClaw persists session state inside its workspace/.openclaw dir.
        workspace = (
            ((data.get("agents") or {}).get("defaults") or {}).get("workspace")
            or os.path.expanduser("~/.openclaw/workspace")
        )
        os.makedirs(os.path.join(workspace, ".openclaw"), exist_ok=True)

        stable_user = f"researchclaw:{self.config.session_name}"
        return url, token, stable_user

    @staticmethod
    def _probe_gateway_socket(url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port
        if not host or port is None:
            return False
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            return False

    def _send_prompt_via_openclaw_gateway(self, prompt: str) -> str:
        """Use OpenClaw's local HTTP API with a stable session-backed user id."""
        resolved = self._load_openclaw_gateway_config()
        if not resolved:
            raise RuntimeError("OpenClaw gateway config not available")
        url, token, stable_user = resolved
        gateway_timeout = max(
            60,
            int(getattr(self.config, "gateway_timeout_sec", 900) or 900),
        )

        body = json.dumps({
            "model": "openclaw/default",
            "user": stable_user,
            "input": prompt,
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-openclaw-agent-id": "main",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=gateway_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenClaw gateway request failed (HTTP {exc.code}): {detail}"
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(
                f"OpenClaw gateway request timed out after {gateway_timeout}s"
            ) from exc
        except http.client.RemoteDisconnected as exc:
            raise RuntimeError(f"OpenClaw gateway request disconnected: {exc}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenClaw gateway request failed: {exc}") from exc

        if payload.get("status") == "failed":
            error = payload.get("error") or {}
            raise RuntimeError(
                f"OpenClaw gateway response failed: {error.get('message') or error}"
            )

        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        outputs = payload.get("output") or []
        for item in outputs:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                    text = part["text"].strip()
                    if text:
                        return text

        raise RuntimeError("OpenClaw gateway returned no output_text")

    @staticmethod
    def _is_gateway_timeout_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "openclaw gateway request timed out" in text
            or "gateway timed out" in text
        )

    def _send_prompt_via_file(self, acpx: str, prompt: str) -> str:
        """Write prompt to a temp file, ask the agent to read and respond."""
        fd, prompt_path = tempfile.mkstemp(
            suffix=".md", prefix="rc_prompt_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)

            short_prompt = (
                f"Read the file at {prompt_path} in its entirety. "
                f"Follow ALL instructions contained in that file and "
                f"respond exactly as requested. Do NOT summarize, "
                f"just produce the requested output."
            )

            try:
                result = subprocess.run(
                    [acpx, "--approve-all", "--ttl", "0", "--cwd", self._abs_cwd(),
                     self.config.agent, "-s", self.config.session_name,
                     short_prompt],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=self.config.timeout_sec,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"ACP prompt timed out after {self.config.timeout_sec}s"
                ) from exc

            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                raise RuntimeError(
                    f"ACP prompt failed (exit {result.returncode}): {stderr}"
                )

            return self._extract_response(result.stdout)
        finally:
            try:
                os.unlink(prompt_path)
            except OSError:
                pass

    @staticmethod
    def _extract_response(raw_output: str | None) -> str:
        """Extract the agent's actual response from acpx output.

        Strips acpx metadata lines ([client], [acpx], [tool], [done])
        and their continuation lines (indented or sub-field lines like
        ``input:``, ``output:``, ``files:``, ``kind:``).
        """
        if not raw_output:
            return ""
        lines: list[str] = []
        in_tool_block = False
        for line in raw_output.splitlines():
            # Skip acpx control lines
            if _DONE_RE.match(line) or _CLIENT_RE.match(line) or _ACPX_RE.match(line):
                in_tool_block = False
                continue
            if _TOOL_RE.match(line):
                in_tool_block = True
                continue
            # Tool blocks have indented continuation lines
            if in_tool_block:
                if line.startswith("  ") or not line.strip():
                    continue
                # Non-indented, non-empty line = end of tool block
                in_tool_block = False
            # Skip empty lines at start
            if not lines and not line.strip():
                continue
            lines.append(line)

        # Trim trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()

        return "\n".join(lines)

    @staticmethod
    def _messages_to_prompt(
        messages: list[dict[str, str]],
        *,
        system: str | None = None,
    ) -> str:
        """Flatten a chat-messages list into a single text prompt.

        Preserves role labels so the agent can distinguish context.
        """
        parts: list[str] = []
        if system:
            parts.append(f"[System]\n{system}")
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System]\n{content}")
            elif role == "assistant":
                parts.append(f"[Previous Response]\n{content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)
