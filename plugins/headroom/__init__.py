"""Headroom plugin for Hermes Agent.

Reproduces the headroom-ai integration from Claude Code:

1. on_session_start  — health-check the headroom proxy; warn if unreachable
2. pre_llm_call      — inject a one-line CCR reminder so the LLM knows to call
                       headroom_retrieve when it encounters <<ccr:...>> markers
3. /headroom command — status, enable/disable CCR reminder injection

The proxy itself (http://127.0.0.1:8787) handles compression and CCR marker
insertion.  This plugin only ensures the agent uses it correctly.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PROXY_URL = "http://127.0.0.1:8787"
_INJECT_ENABLED = True

_CCR_HINT = (
    "Note: tool results may contain <<ccr:HASH>> compression markers. "
    "Call headroom_retrieve(hash=HASH) to get the original content."
)


# ---------------------------------------------------------------------------
# Proxy health check
# ---------------------------------------------------------------------------

def _proxy_health() -> Optional[dict]:
    """GET /health from the headroom proxy. Returns parsed JSON or None."""
    try:
        req = urllib.request.Request(f"{_PROXY_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _on_session_start(**_: Any) -> None:
    """Check headroom proxy health at session start."""
    health = _proxy_health()
    if health is None:
        logger.warning(
            "[headroom] Proxy at %s is unreachable — compression disabled. "
            "Start it with: cd ~/mcpserver && docker compose up -d headroom",
            _PROXY_URL,
        )
        return

    status = health.get("status", "unknown")
    version = health.get("version", "?")
    uptime = int(health.get("uptime_seconds", 0))
    compress = health.get("runtime", {}).get("anthropic_pre_upstream", {}).get("enabled", False)

    logger.info(
        "[headroom] Proxy v%s — status=%s uptime=%ds compression=%s",
        version, status, uptime, "on" if compress else "off",
    )

    if status != "healthy":
        logger.warning("[headroom] Proxy reports status=%s", status)


def _on_pre_llm_call(**kwargs: Any) -> Optional[str]:
    """Inject a CCR reminder into the user message when enabled."""
    if not _INJECT_ENABLED:
        return None
    return _CCR_HINT


# ---------------------------------------------------------------------------
# /headroom slash command
# ---------------------------------------------------------------------------

def _handle_slash(raw_args: str) -> str:
    global _INJECT_ENABLED

    argv = raw_args.strip().split()
    sub = argv[0] if argv else "status"

    if sub in ("status", ""):
        health = _proxy_health()
        if health is None:
            proxy_line = f"Proxy {_PROXY_URL}: UNREACHABLE"
        else:
            v = health.get("version", "?")
            s = health.get("status", "?")
            uptime = int(health.get("uptime_seconds", 0))
            compress = health.get("runtime", {}).get(
                "anthropic_pre_upstream", {}
            ).get("enabled", False)
            proxy_line = (
                f"Proxy {_PROXY_URL}: {s} | v{v} | uptime {uptime}s | "
                f"compression {'ON' if compress else 'OFF'}"
            )
        inject_line = f"CCR hint injection: {'enabled' if _INJECT_ENABLED else 'disabled'}"
        return f"{proxy_line}\n{inject_line}"

    if sub == "enable":
        _INJECT_ENABLED = True
        return "CCR hint injection enabled."

    if sub == "disable":
        _INJECT_ENABLED = False
        return "CCR hint injection disabled."

    if sub == "health":
        health = _proxy_health()
        if health is None:
            return f"Proxy {_PROXY_URL} is not reachable."
        return json.dumps(health, indent=2)

    return (
        "Usage: /headroom [status|enable|disable|health]\n"
        "  status   — proxy health + injection state (default)\n"
        "  enable   — enable CCR hint injection before each LLM call\n"
        "  disable  — disable CCR hint injection\n"
        "  health   — raw proxy /health JSON"
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(ctx: Any) -> None:
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_command(
        "headroom",
        handler=_handle_slash,
        description="Headroom proxy status and CCR hint injection control.",
    )
    logger.info("[headroom] plugin registered (proxy=%s)", _PROXY_URL)


__all__ = ["register"]
