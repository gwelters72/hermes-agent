"""no-autotitle — suppress automatic session title generation.

After the first exchange, Hermes fires a background thread that calls
maybe_auto_title(), which in turn makes an auxiliary LLM call to name
the session. This plugin replaces maybe_auto_title with a no-op at load
time so the auxiliary call is never made.

All four call sites (cli.py, gateway/run.py, acp_adapter/server.py,
tui_gateway/server.py) use lazy imports inside their functions, so they
resolve the patched symbol when they execute — not at module load time.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register(ctx) -> None:  # noqa: ANN001
    import agent.title_generator as _tg

    _tg.maybe_auto_title = lambda *args, **kwargs: None
    logger.info("no-autotitle: session title generation disabled")
