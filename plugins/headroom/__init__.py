"""Headroom plugin — compress context tokens before API requests.

Headroom (headroomlabs.ai) compresses boilerplate in tool calls, DB queries,
file reads, and RAG retrievals — achieving 70-95% token reduction while
preserving answer quality. Same answers, fraction of the tokens.

This plugin integrates the Headroom compressor into Hermes Agent via:
1. pre_api_request hook — intercepts messages, compresses them
2. post_api_request hook — logs compression stats
3. /headroom slash command — status, toggle, metrics

All compression is transparent to the agent and user.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ENABLED = True  # Toggle via /headroom command
_STATS = {"compressed": 0, "total": 0, "tokens_saved": 0}


def _get_headroom_compress():
    """Lazy-import headroom.compress. Returns None if not installed."""
    try:
        from headroom import compress
        return compress
    except ImportError:
        return None


def _on_pre_api_request(
    provider: str = "",
    model: str = "",
    messages: Optional[list] = None,
    **_: Any,
) -> Optional[Dict[str, Any]]:
    """Compress messages before API request if headroom is enabled."""
    if not _ENABLED or not messages:
        return None

    compress = _get_headroom_compress()
    if not compress:
        logger.warning("Headroom not installed. Install: pip install headroom-ai[all]")
        return None

    try:
        # Headroom compress() returns result with .messages and .stats
        result = compress(messages, model=model)

        _STATS["total"] += 1
        if hasattr(result, "messages") and result.messages:
            _STATS["compressed"] += 1
            # Try to extract token savings if available
            if hasattr(result, "stats") and result.stats:
                if "tokens_saved" in result.stats:
                    _STATS["tokens_saved"] += result.stats["tokens_saved"]

            logger.debug(
                f"[Headroom] Compressed {len(messages)} messages → "
                f"{len(result.messages)} (model={model})"
            )
            return {"messages": result.messages}
    except Exception as e:
        logger.warning(f"Headroom compression failed: {e}")
        return None

    return None


def _on_post_api_request(
    provider: str = "",
    model: str = "",
    response: Any = None,
    **_: Any,
) -> None:
    """Log API request completion (for metrics)."""
    if not _ENABLED:
        return
    # Placeholder for future post-processing (e.g., decompression stats)


# ---------------------------------------------------------------------------
# Slash command
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
/headroom — Headroom context compression

Subcommands:
  status          Show compression stats and toggle status
  enable          Turn compression on
  disable         Turn compression off
  reset-stats     Reset compression counters

Headroom compresses boilerplate in tool calls, DB queries, file reads,
and RAG retrievals — achieving 70–95% reduction while preserving answers.

Install: pip install headroom-ai[all]
Docs: https://headroomlabs.ai/docs
"""


def _handle_slash(raw_args: str) -> Optional[str]:
    global _ENABLED, _STATS

    argv = raw_args.strip().split()
    sub = argv[0] if argv else "status"

    if sub in ("help", "-h", "--help"):
        return _HELP_TEXT

    if sub == "status":
        status = "✓ Enabled" if _ENABLED else "✗ Disabled"
        return (
            f"Headroom compression is {status}\n"
            f"Requests: {_STATS['total']}\n"
            f"Compressed: {_STATS['compressed']}\n"
            f"Tokens saved: {_STATS['tokens_saved']:,}"
        )

    if sub == "enable":
        _ENABLED = True
        return "✓ Headroom compression enabled"

    if sub == "disable":
        _ENABLED = False
        return "✗ Headroom compression disabled"

    if sub == "reset-stats":
        _STATS = {"compressed": 0, "total": 0, "tokens_saved": 0}
        return "Stats reset"

    return f"Unknown subcommand: {sub}\n\n{_HELP_TEXT}"


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:
    """Register Headroom plugin hooks and slash command."""
    ctx.register_hook("pre_api_request", _on_pre_api_request)
    ctx.register_hook("post_api_request", _on_post_api_request)
    ctx.register_command(
        "headroom",
        handler=_handle_slash,
        description="Compress context tokens using Headroom before API requests.",
    )
    logger.info("Headroom plugin registered (compression %s)",
                "enabled" if _ENABLED else "disabled")
