# Headroom Plugin for Hermes Agent

Integrates [Headroom](https://headroomlabs.ai) context compression into Hermes Agent, reducing token usage by 70–95% while preserving answer quality.

## Features

- **Automatic compression** – Intercepts API requests, compresses messages transparently
- **Zero overhead** – No agent or user interaction needed; runs as a silent hook
- **Metrics tracking** – Monitors compression efficiency and token savings
- **Easy toggle** – Enable/disable compression with `/headroom` commands

## Installation

### 1. Install Headroom

```bash
pip install "headroom-ai[all]"
```

Or to the Hermes venv:

```bash
~/.hermes/venv/bin/pip install "headroom-ai[all]"
```

### 2. The plugin is already in place

The plugin directory exists at `~/dev/hermes-agent/plugins/headroom/` and is automatically discovered when you run Hermes Agent.

## Usage

### Basic Commands

```bash
/headroom status          # Show compression stats and toggle status
/headroom enable          # Turn compression on (default)
/headroom disable         # Turn compression off
/headroom reset-stats     # Reset compression counters
```

### Example Session

```
You: /headroom status
Hermes:
  Headroom compression is ✓ Enabled
  Requests: 42
  Compressed: 40
  Tokens saved: 18,752
```

## How It Works

1. **pre_api_request hook** – Before sending messages to Claude, Anthropic, OpenAI, etc., the plugin calls `headroom.compress()` on the message batch
2. **Compression** – Headroom's `CacheAligner`, `ContentRouter`, and `IntelligentContext` compress boilerplate:
   - Tool call schemas → optimized
   - JSON payloads → deduplicated
   - Code snippets → AST-aware compression
   - Log dumps → relevant lines only
3. **Transparent** – The compressed messages are substituted into the API request; the agent sees the same answers

## Configuration

The plugin is enabled by default. It respects:

- **Module-level `_ENABLED` flag** – Set to `False` to disable on startup (edit `__init__.py` for permanent config)
- **Slash commands** – `/headroom disable` to toggle at runtime
- **Fallback behavior** – If Headroom is not installed, the plugin warns and lets requests pass through uncompressed

## Metrics

The plugin tracks:
- `total` – Total API requests processed
- `compressed` – Successful compressions
- `tokens_saved` – Approximate tokens reduced by Headroom

View with `/headroom status`.

## Troubleshooting

### "Headroom not installed" warning

Install Headroom:
```bash
pip install "headroom-ai[all]"
```

Or to the Hermes venv:
```bash
~/.hermes/venv/bin/pip install "headroom-ai[all]"
```

### Compression not activating

Check:
1. Plugin is loaded: `hermes /plugins` (should list `headroom`)
2. Compression is enabled: `/headroom status` (should show `✓ Enabled`)
3. Headroom is installed: `python -c "from headroom import compress; print('OK')"`

### Disable compression temporarily

```bash
/headroom disable
# ... run agent ...
/headroom enable
```

## Links

- **Headroom Labs**: https://headroomlabs.ai
- **GitHub**: https://github.com/headroomlabs/headroom
- **Docs**: https://headroomlabs.ai/docs
- **Discord**: https://discord.gg/headroom (community support)

---

**Built for Hermes Agent** by integrating Headroom's public API and hooks system.
