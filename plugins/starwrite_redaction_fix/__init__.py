"""starwrite_redaction_fix — stop the secret redactor from mangling file content.

Problem
-------
``agent.redact.redact_sensitive_text`` is applied to *tool-call arguments* before
they enter conversation history / context compression
(``agent/chat_completion_helpers.py``, ``agent/context_compressor.py``). Its
ENV-assignment, JSON-field and Authorization-header maskers fire on perfectly
legitimate source code, replacing it with ``***``:

    MAX_TOKENS=4096                  -> MAX_TOKENS=***
    API_KEY=test                     -> API_KEY=***
    {"apiKey": "test"}               -> {"apiKey": "***"}
    h = "Authorization: Bearer " ...  -> h = "Authorization: Bearer ***   (breaks the string)

The model then sees the ``***`` version of its own write in history (or after
compression) and re-emits the corrupted content on the next edit — so files with
``***`` "can never be written". The base64 ``safe_write`` workaround only worked
because base64 contains no secret-shaped substrings.

Fix
---
Wrap ``redact_sensitive_text`` so that when the input is a **write_file /
execute_code / patch** tool-call argument, the content/code field is preserved
verbatim (it is destined for the user's own filesystem, not an external log).
All other inputs — log lines, ``terminal`` command arguments (the #19798
"curl -H 'Authorization: Bearer sk-...'" defence), tool output — are redacted
exactly as before.

Plugin-only, no core patch. Opt out with ``HERMES_STARWRITE_FIX=0``.
"""

import json
import logging
import sys

logger = logging.getLogger(__name__)

_SENTINEL = "_starwrite_redaction_wrapped"

# A tool-call argument string is treated as "file content" (and thus exempt
# from the false-positive maskers) only if it is clearly a write/code/patch
# payload — never a plain terminal command.
_WRITE_HINTS = ('"content"', '"code"', '"file_text"', '"new_str"', '"new_string"')
_PATCH_HINTS = ("*** Begin Patch", "*** Update File:", "*** Add File:")


def _is_file_payload(text: str) -> bool:
    """True if `text` is a write_file/execute_code/patch tool-call argument.

    Cheap substring gate first, then a strict structural check so that e.g. a
    `terminal` command containing the word "content" is NOT exempted.
    """
    if not isinstance(text, str) or not text:
        return False

    # V4A patch payloads (not JSON) — apply-patch format.
    for h in _PATCH_HINTS:
        if h in text:
            return True

    # JSON tool-call arguments.
    if not any(h in text for h in _WRITE_HINTS):
        return False
    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return False
    try:
        obj = json.loads(stripped)
    except (ValueError, TypeError):
        return False
    if not isinstance(obj, dict):
        return False
    # write_file: needs a content field + a path-like field.
    if "content" in obj and ("path" in obj or "file_path" in obj):
        return True
    # execute_code: a code field.
    if "code" in obj and isinstance(obj.get("code"), str):
        return True
    # apply_patch / str-replace style edits.
    if any(k in obj for k in ("file_text", "new_str", "new_string", "patch")):
        return True
    return False


def _install(ctx=None) -> bool:
    from utils import env_var_enabled  # Hermes helper, present in repo

    import os
    if not env_var_enabled("HERMES_STARWRITE_FIX") and os.getenv("HERMES_STARWRITE_FIX") is not None:
        logger.info("starwrite_redaction_fix: disabled via HERMES_STARWRITE_FIX=0")
        return False

    import agent.redact as redact_mod

    original = getattr(redact_mod, "redact_sensitive_text")
    if getattr(original, _SENTINEL, False):
        return True  # already wrapped (idempotent)

    def redact_sensitive_text(text, *args, **kwargs):
        if _is_file_payload(text):
            return text  # preserve file/code/patch content verbatim
        return original(text, *args, **kwargs)

    setattr(redact_sensitive_text, _SENTINEL, True)
    redact_sensitive_text.__wrapped__ = original

    # 1) Patch the canonical module attribute (covers in-function imports such
    #    as agent/chat_completion_helpers.py which re-imports at call time).
    redact_mod.redact_sensitive_text = redact_sensitive_text

    # 2) Re-bind every module that did `from agent.redact import
    #    redact_sensitive_text` at import time (e.g. agent.context_compressor),
    #    since that captured the original by value.
    rebound = 0
    for mod in list(sys.modules.values()):
        if mod is None or mod is redact_mod:
            continue
        if getattr(mod, "redact_sensitive_text", None) is original:
            try:
                setattr(mod, "redact_sensitive_text", redact_sensitive_text)
                rebound += 1
            except Exception:
                pass

    logger.info(
        "starwrite_redaction_fix: active — file/code/patch content exempt from "
        "secret redaction (rebound in %d already-imported module(s))", rebound,
    )
    return True


def register(ctx):
    """Hermes plugin entry point."""
    _install(ctx)
