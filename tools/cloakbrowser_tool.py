#!/usr/bin/env python3
"""
CloakBrowser Tool Module

Drop-in replacement for the built-in browser tools, powered by CloakBrowser
(stealth Chromium that passes bot detection). Registers the same 10 tools
(browser_navigate, browser_snapshot, browser_click, browser_type,
browser_console, browser_vision, browser_scroll, browser_back,
browser_press, browser_get_images) but uses CloakBrowser's Python API
internally.

Usage:
    from tools.cloakbrowser_tool import browser_navigate, browser_snapshot, browser_click

    result = browser_navigate("https://example.com", task_id="task_123")
    snapshot = browser_snapshot(task_id="task_123")
    browser_click("@e5", task_id="task_123")

Configuration:
    - headless: Set via CLOAKBROWSER_HEADLESS env var (default: True)
    - humanize: Set via CLOAKBROWSER_HUMANIZE env var (default: False)
    - proxy: Set via CLOAKBROWSER_PROXY env var (default: None, supports http:// and socks5://)
    - geoip: Set via CLOAKBROWSER_GEOIP env var (default: False)
    - tor: Set via CLOAKBROWSER_TOR env var (default: False, uses socks5://127.0.0.1:9050)
"""

import json
import logging
import os
import re
import atexit
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path

from tools.registry import registry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State management — one browser instance per task_id
# ---------------------------------------------------------------------------

_browser_instances: Dict[str, Any] = {}
_page_instances: Dict[str, Any] = {}
_lock = threading.Lock()

# Global config from environment
_HEADLESS: bool = os.environ.get("CLOAKBROWSER_HEADLESS", "true").lower() in ("true", "1", "yes")
_HUMANIZE: bool = os.environ.get("CLOAKBROWSER_HUMANIZE", "false").lower() in ("true", "1", "yes")
_TOR: bool = os.environ.get("CLOAKBROWSER_TOR", "false").lower() in ("true", "1", "yes")
_PROXY: Optional[str] = os.environ.get("CLOAKBROWSER_PROXY") or None
_GEOIP: bool = os.environ.get("CLOAKBROWSER_GEOIP", "false").lower() in ("true", "1", "yes")
_TOR_SOCKS_PORT: int = int(os.environ.get("CLOAKBROWSER_TOR_PORT", "9050"))
_TOR_SOCKS_ADDR: str = os.environ.get("CLOAKBROWSER_TOR_HOST", "127.0.0.1")


def _is_tor_available() -> bool:
    """Check if Tor SOCKS5 proxy is reachable."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((_TOR_SOCKS_ADDR, _TOR_SOCKS_PORT))
        s.close()
        return True
    except Exception:
        return False


def _get_launch_kwargs() -> dict:
    """Build launch kwargs from environment config."""
    kwargs = {"headless": _HEADLESS}
    if _HUMANIZE:
        kwargs["humanize"] = True
    if _TOR:
        proxy_url = f"socks5://{_TOR_SOCKS_ADDR}:{_TOR_SOCKS_PORT}"
        if _is_tor_available():
            kwargs["proxy"] = proxy_url
            logger.info("CloakBrowser: Tor SOCKS5 proxy enabled (%s)", proxy_url)
        else:
            logger.warning("CloakBrowser: Tor enabled but SOCKS5 port %d not reachable", _TOR_SOCKS_PORT)
    elif _PROXY:
        kwargs["proxy"] = _PROXY
    if _GEOIP:
        kwargs["geoip"] = True
    return kwargs


def _ensure_browser(task_id: str):
    """Ensure a browser and page exist for the given task_id."""
    with _lock:
        if task_id not in _browser_instances or _browser_instances[task_id] is None:
            try:
                from cloakbrowser import launch
                browser = launch(**_get_launch_kwargs())
                _browser_instances[task_id] = browser
            except ImportError:
                raise RuntimeError(
                    "cloakbrowser not installed. Run: pip install cloakbrowser && cloakbrowser install"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to launch CloakBrowser: {e}")

        if task_id not in _page_instances or _page_instances[task_id] is None:
            try:
                page = _browser_instances[task_id].new_page()
                _page_instances[task_id] = page
            except Exception as e:
                raise RuntimeError(f"Failed to create page: {e}")


def _get_page(task_id: str):
    """Get or create the page for task_id."""
    _ensure_browser(task_id)
    return _page_instances[task_id]


def _cleanup_browser(task_id: str):
    """Clean up browser and page for task_id."""
    with _lock:
        page = _page_instances.pop(task_id, None)
        browser = _browser_instances.pop(task_id, None)
        if page:
            try:
                page.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def _cleanup_all():
    """Clean up all browser instances on exit."""
    for task_id in list(_browser_instances.keys()):
        _cleanup_browser(task_id)


atexit.register(_cleanup_all)


# ---------------------------------------------------------------------------
# Helper: Convert CloakBrowser page to accessibility-tree-like snapshot
# ---------------------------------------------------------------------------

def _page_to_snapshot(page) -> str:
    """
    Convert a CloakBrowser page to an accessibility-tree-like snapshot
    matching the format of the built-in browser tools.
    """
    try:
        # Get the full accessibility tree
        aria = page.evaluate("""
            () => {
                const nodes = [];
                const root = document.body;
                function walk(node, depth = 0) {
                    if (!node || node.nodeType !== 1) return;
                    const tag = node.tagName ? node.tagName.toLowerCase() : '';
                    const role = node.getAttribute('role') || '';
                    const label = node.getAttribute('aria-label') || node.textContent?.trim()?.slice(0, 80) || '';
                    const id = node.id ? `#${node.id}` : '';
                    const cls = node.className ? `.${String(node.className).split(' ')[0]}` : '';
                    const visible = node.offsetWidth > 0 && node.offsetHeight > 0;
                    if (!visible) return;
                    const indent = '  '.repeat(depth);
                    const attrs = [];
                    if (role) attrs.push(`role="${role}"`);
                    if (id) attrs.push(id);
                    if (cls) attrs.push(cls);
                    const inputType = node.type ? ` type="${node.type}"` : '';
                    const name = node.name ? ` name="${node.name}"` : '';
                    const placeholder = node.placeholder ? ` placeholder="${node.placeholder}"` : '';
                    const checked = node.checked !== undefined ? ` ${node.checked ? 'checked' : ''}` : '';
                    const clickable = node.onclick || node.tagName === 'A' || node.tagName === 'BUTTON' ||
                        node.tagName === 'INPUT' || node.getAttribute('role') === 'button' ||
                        node.getAttribute('tabindex') === '0';
                    const ref = `@e${nodes.length + 1}`;
                    let line = `${indent}[${ref}] ${tag}${id}${cls}${inputType}${name}${placeholder}${checked}`;
                    if (label && !role && !id && !cls) {
                        line += ` "${label}"`;
                    }
                    if (clickable) line += ' (clickable)';
                    nodes.push({ ref, line, element: node });
                    for (const child of node.children) {
                        walk(child, depth + 1);
                    }
                }
                walk(root);
                return nodes.map(n => n.line).join('\\n');
            }
        """)
        return aria or "(empty page)"
    except Exception as e:
        return f"(snapshot error: {e})"


def _find_clickable_elements(page) -> List[dict]:
    """Find all clickable/interactive elements on the page."""
    try:
        elements = page.evaluate("""
            () => {
                const results = [];
                const allEls = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"], ' +
                    '[role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], ' +
                    '[tabindex="0"], [onclick]'
                );
                let counter = 1;
                for (const el of allEls) {
                    if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
                    const tag = el.tagName.toLowerCase();
                    const text = (el.textContent || '').trim().slice(0, 100);
                    const ref = `@e${counter}`;
                    results.push({
                        ref,
                        tag,
                        text,
                        id: el.id || '',
                        name: el.name || '',
                        type: el.type || '',
                        role: el.getAttribute('role') || ''
                    });
                    counter++;
                }
                return results;
            }
        """)
        return elements or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def browser_navigate(url: str, task_id: str = "default", **kwargs) -> str:
    """Navigate to a URL.

    Args:
        url: The URL to navigate to.
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(task_id)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = page.title()
        current_url = page.url
        return json.dumps({
            "success": True,
            "url": current_url,
            "title": title,
            "message": f"Navigated to {current_url} (title: {title})"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_snapshot(task_id: str = "default", full: bool = False, **kwargs) -> str:
    """Get a text-based snapshot of the current page.

    Args:
        task_id: Session identifier (default: "default").
        full: If True, return full content (ignored for CloakBrowser).
    """
    try:
        page = _get_page(task_id)
        snapshot = _page_to_snapshot(page)
        # Add clickable element list at the end
        elements = _find_clickable_elements(page)
        if elements:
            clickable_info = "\n\n--- Interactive Elements ---\n"
            for el in elements:
                clickable_info += f"  {el['ref']}: <{el['tag']}> {el['text'][:60]} (id={el['id']}, name={el['name']}, type={el['type']})\n"
            snapshot += clickable_info
        return snapshot
    except Exception as e:
        return f"(snapshot error: {e})"


def browser_click(ref: str, task_id: str = "default", **kwargs) -> str:
    """Click an element identified by its ref ID.

    Args:
        ref: Element reference (e.g., "@e5").
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(task_id)
        # Parse ref — remove @ prefix if present
        ref_clean = ref.lstrip("@")
        # Try to find element by ref
        element = page.evaluate(f"""
            () => {{
                // Try direct ref match
                const allEls = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"], ' +
                    '[role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], ' +
                    '[tabindex="0"], [onclick]'
                );
                let counter = 1;
                for (const el of allEls) {{
                    if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
                    if (counter === {ref_clean}) return el;
                    counter++;
                }}
                return null;
            }}
        """)
        if element is None:
            return json.dumps({"success": False, "error": f"Element {ref} not found"})

        # Click the element
        page.evaluate(f"""
            () => {{
                const allEls = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"], ' +
                    '[role="tab"], [role="menuitem"], [role="checkbox"], [role="radio"], ' +
                    '[tabindex="0"], [onclick]'
                );
                let counter = 1;
                for (const el of allEls) {{
                    if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
                    if (counter === {ref_clean}) {{
                        el.click();
                        return 'clicked';
                    }}
                    counter++;
                }}
                return 'not found';
            }}
        """)
        return json.dumps({"success": True, "message": f"Clicked element {ref}"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_type(ref: str, text: str, task_id: str = "default", **kwargs) -> str:
    """Type text into an input field.

    Args:
        ref: Element reference (e.g., "@e3").
        text: Text to type.
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(task_id)
        ref_clean = ref.lstrip("@")
        page.evaluate(f"""
            () => {{
                const allEls = document.querySelectorAll(
                    'input, textarea, [contenteditable="true"]'
                );
                let counter = 1;
                for (const el of allEls) {{
                    if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
                    if (counter === {ref_clean}) {{
                        el.focus();
                        el.value = '';
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return 'typed';
                    }}
                    counter++;
                }}
                return 'not found';
            }}
        """)
        # Type the text character by character for realism
        for char in text:
            page.keyboard.type(char, delay=50)
        return json.dumps({"success": True, "message": f"Typed '{text}' into {ref}"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_console(clear: bool = False, expression: Optional[str] = None, **kwargs) -> str:
    """Get browser console output.

    Args:
        clear: If True, clear console after reading.
        expression: JavaScript expression to evaluate.
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(kwargs.get("task_id", "default"))
        if expression:
            result = page.evaluate(expression)
            return json.dumps({"console": str(result), "expression": expression})
        # Get console messages
        messages = page.evaluate("""
            () => {
                return 'No console capture available in headless mode. Use expression parameter for JS evaluation.';
            }
        """)
        return json.dumps({"console": messages})
    except Exception as e:
        return json.dumps({"error": str(e)})


def browser_vision(question: Optional[str] = None, annotate: bool = False, **kwargs) -> str:
    """Take a screenshot of the page.

    Args:
        question: Optional question about the page.
        annotate: If True, overlay numbered labels on interactive elements.
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(kwargs.get("task_id", "default"))
        screenshot_path = f"/tmp/cloakbrowser_screenshot_{kwargs.get('task_id', 'default')}.png"
        page.screenshot(path=screenshot_path, full_page=True)
        result = {
            "screenshot_path": screenshot_path,
            "url": page.url,
            "title": page.title(),
        }
        if question:
            result["question"] = question
        if annotate:
            elements = _find_clickable_elements(page)
            result["interactive_elements"] = elements
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def browser_scroll(direction: str, **kwargs) -> str:
    """Scroll the page.

    Args:
        direction: "up" or "down".
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(kwargs.get("task_id", "default"))
        page.evaluate(f"""
            () => {{
                window.scrollBy(0, {500 if direction == 'down' else -500});
                return 'scrolled {direction}';
            }}
        """)
        return json.dumps({"success": True, "message": f"Scrolled {direction}"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_back(**kwargs) -> str:
    """Navigate back in browser history.

    Args:
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(kwargs.get("task_id", "default"))
        page.go_back()
        return json.dumps({
            "success": True,
            "url": page.url,
            "title": page.title(),
            "message": f"Navigation back to {page.url}"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_press(key: str, **kwargs) -> str:
    """Press a keyboard key.

    Args:
        key: Key to press (e.g., "Enter", "Tab", "Escape", "ArrowDown").
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(kwargs.get("task_id", "default"))
        page.keyboard.press(key)
        return json.dumps({"success": True, "message": f"Pressed {key}"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def browser_get_images(**kwargs) -> str:
    """Get a list of all images on the current page.

    Args:
        task_id: Session identifier (default: "default").
    """
    try:
        page = _get_page(kwargs.get("task_id", "default"))
        images = page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('img');
                return Array.from(imgs).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.naturalWidth,
                    height: img.naturalHeight,
                    visible: img.offsetWidth > 0 && img.offsetHeight > 0
                }));
            }
        """)
        return json.dumps({"images": images or []})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool registration — override built-in browser tools
# ---------------------------------------------------------------------------

registry.register(
    name="browser_navigate",
    toolset="browser",
    schema={
        "name": "browser_navigate",
        "description": "Navigate to a URL in the browser. Initializes the session and loads the page. Must be called before other browser tools. Returns a compact page snapshot with interactive elements and ref IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to (e.g., 'https://example.com')"},
                "task_id": {"type": "string", "description": "Session identifier (default: 'default')", "default": "default"}
            },
            "required": ["url"]
        }
    },
    handler=lambda args, **kw: browser_navigate(
        url=args.get("url", ""), task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_snapshot",
    toolset="browser",
    schema={
        "name": "browser_snapshot",
        "description": "Get a text-based snapshot of the current page's accessibility tree. Returns interactive elements with ref IDs (like @e1, @e2) for browser_click and browser_type. full=false (default): compact view with interactive elements only. full=true: complete page content. Snapshots over 8000 chars are truncated. Requires browser_navigate first.",
        "parameters": {
            "type": "object",
            "properties": {
                "full": {"type": "boolean", "description": "If true, returns complete page content. If false (default), returns compact view with interactive elements only.", "default": False},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            }
        }
    },
    handler=lambda args, **kw: browser_snapshot(
        task_id=args.get("task_id", "default"), full=args.get("full", False)),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_click",
    toolset="browser",
    schema={
        "name": "browser_click",
        "description": "Click on an element identified by its ref ID from the snapshot (e.g., '@e5'). The ref IDs are shown in square brackets in the snapshot output. Requires browser_navigate and browser_snapshot to be called first.",
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "The element reference from the snapshot (e.g., '@e5', '@e12')"},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            },
            "required": ["ref"]
        }
    },
    handler=lambda args, **kw: browser_click(
        ref=args.get("ref", ""), task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_type",
    toolset="browser",
    schema={
        "name": "browser_type",
        "description": "Type text into an input field identified by its ref ID. Clears the field first, then types the new text. Requires browser_navigate and browser_snapshot to be called first.",
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "The element reference from the snapshot (e.g., '@e3')"},
                "text": {"type": "string", "description": "The text to type into the field"},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            },
            "required": ["ref", "text"]
        }
    },
    handler=lambda args, **kw: browser_type(
        ref=args.get("ref", ""), text=args.get("text", ""),
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_console",
    toolset="browser",
    schema={
        "name": "browser_console",
        "description": "Get browser console output and JavaScript errors from the current page. Returns console.log/warn/error/info messages and uncaught JS exceptions. Use this to detect silent JavaScript errors, failed API calls, and application warnings. Requires browser_navigate to be called first. When 'expression' is provided, evaluates JavaScript in the page context and returns the result.",
        "parameters": {
            "type": "object",
            "properties": {
                "clear": {"type": "boolean", "description": "If true, clear the message buffers after reading", "default": False},
                "expression": {"type": "string", "description": "JavaScript expression to evaluate in the page context."},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            }
        }
    },
    handler=lambda args, **kw: browser_console(
        clear=args.get("clear", False), expression=args.get("expression"),
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_vision",
    toolset="browser",
    schema={
        "name": "browser_vision",
        "description": "Take a screenshot of the current page so you can inspect it visually. Use this when you need to understand what the page looks like - especially for CAPTCHAs, visual verification challenges, complex layouts, or cases where the text snapshot misses important visual information. Includes a screenshot_path that you can share with the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What you want to know about the page visually. Be specific about what you're looking for."},
                "annotate": {"type": "boolean", "description": "If true, overlay numbered [N] labels on interactive elements.", "default": False},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            },
            "required": ["question"]
        }
    },
    handler=lambda args, **kw: browser_vision(
        question=args.get("question", ""), annotate=args.get("annotate", False),
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_scroll",
    toolset="browser",
    schema={
        "name": "browser_scroll",
        "description": "Scroll the page in a direction. Use this to reveal more content that may be below or above the current viewport. Requires browser_navigate to be called first.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "description": "Direction to scroll"},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            },
            "required": ["direction"]
        }
    },
    handler=lambda args, **kw: browser_scroll(
        direction=args.get("direction", "down"),
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_back",
    toolset="browser",
    schema={
        "name": "browser_back",
        "description": "Navigate back to the previous page in browser history. Requires browser_navigate to be called first.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            }
        }
    },
    handler=lambda args, **kw: browser_back(
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_press",
    toolset="browser",
    schema={
        "name": "browser_press",
        "description": "Press a keyboard key. Useful for submitting forms (Enter), navigating (Tab), or keyboard shortcuts. Requires browser_navigate to be called first.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to press (e.g., 'Enter', 'Tab', 'Escape', 'ArrowDown')"},
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            },
            "required": ["key"]
        }
    },
    handler=lambda args, **kw: browser_press(
        key=args.get("key", ""),
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

registry.register(
    name="browser_get_images",
    toolset="browser",
    schema={
        "name": "browser_get_images",
        "description": "Get a list of all images on the current page with their URLs and alt text. Useful for finding images to analyze with the vision tool. Requires browser_navigate to be called first.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Session identifier", "default": "default"}
            }
        }
    },
    handler=lambda args, **kw: browser_get_images(
        task_id=args.get("task_id", "default")),
    check_fn=lambda: True,
    requires_env=["CLOAKBROWSER_HEADLESS"],
    override=True,
)

logger.info("CloakBrowser tool loaded — 10 browser_* tools registered with override=True")
