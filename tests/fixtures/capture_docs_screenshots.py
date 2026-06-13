#!/usr/bin/env python3
"""
Capture documentation screenshots of the signalstripper UI workflow.

Boots the mock server on a loopback port and drives Chromium through the
analyze → select → tally → emit flow, saving element-level PNGs to
docs/images/. Run: uv run python tests/fixtures/capture_docs_screenshots.py
"""
from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from playwright.sync_api import sync_playwright

from signalstripper.mock import mock_profile, mock_summary
from signalstripper.server import create_app

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs" / "images"
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _start_server() -> tuple[str, uvicorn.Server, threading.Thread]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = create_app(Path("/mock/signal.db"), mock_profile(), mock_summary(), mock=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/api/analyze", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    return f"http://127.0.0.1:{port}", server, thread


def _shot(locator, name: str) -> None:
    path = OUT / name
    locator.screenshot(path=str(path))
    print(f"  wrote {path.relative_to(REPO)}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    url, server, thread = _start_server()
    try:
        with sync_playwright() as pw:
            launch = {"headless": True}
            if Path(CHROMIUM).exists():
                launch["executable_path"] = CHROMIUM
            browser = pw.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 1180, "height": 900},
                                    device_scale_factor=2)
            page.goto(url)
            page.wait_for_selector(".thread-card", timeout=10_000)

            # 1. Storage breakdown (analyze output)
            _shot(page.locator("#overview-section"), "01-overview.png")

            # 2. Conversation list, unselected
            _shot(page.locator("#threads-section"), "02-conversations.png")

            # 3. A single selected thread card showing intent + date controls
            first = page.locator(".thread-card").first
            first.click()
            page.wait_for_timeout(150)
            _shot(first, "03-thread-selected.png")

            # 4. Multiple selections incl. a remove-thread, with live tally
            cards = page.locator(".thread-card")
            cards.nth(1).click()
            cards.nth(2).click()
            # set the third selected card's intent to Remove thread
            cards.nth(2).locator(".intent-select").select_option("remove_thread")
            page.wait_for_timeout(150)
            _shot(page.locator("#emit-section"), "04-tally.png")

            # 5. Generated command output
            page.click("#generate-btn")
            output = page.locator("#command-output")
            output.wait_for(state="visible", timeout=5_000)
            page.wait_for_timeout(150)
            _shot(page.locator("#emit-section"), "05-command.png")

            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
