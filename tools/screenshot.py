"""Takes screenshots of the running surf app, one per tab, so you can check how it looks.

Usage (from the project folder, with the virtual environment active):
    pip install -r requirements-dev.txt          # once
    python tools/screenshot.py                   # all tabs, first spot, desktop size
    python tools/screenshot.py --spot Lombok     # a different spot
    python tools/screenshot.py --phone           # phone-sized window

It starts the app itself, opens it in your installed Google Chrome (in the
background, with a temporary profile) and saves PNGs into the screenshots/ folder.
"""
import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parent.parent


def wait_for_server(url, seconds=30):
    """Waits until the app answers, or gives up after `seconds`."""
    for _ in range(seconds * 2):
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"The app did not start at {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spot", help="surf spot to select, e.g. Lombok (default: the first one)")
    parser.add_argument("--phone", action="store_true", help="use a phone-sized window")
    parser.add_argument("--port", type=int, default=8602)
    parser.add_argument("--out", default="screenshots", help="output folder (default: screenshots)")
    args = parser.parse_args()

    out = PROJECT / args.out
    out.mkdir(exist_ok=True)
    url = f"http://localhost:{args.port}"
    # a tall window, because Streamlit scrolls inside the page and a screenshot only shows what fits the window
    size = {"width": 390, "height": 2600} if args.phone else {"width": 1400, "height": 1900}
    suffix = "_phone" if args.phone else ""

    # Start the Streamlit app in the background; it is stopped again at the end.
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(args.port)],
        cwd=PROJECT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(url)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)   # your installed Chrome
            page = browser.new_page(viewport=size)
            page.goto(url)
            page.wait_for_selector("text=Right now at", timeout=60000)

            if args.spot:
                page.get_by_test_id("stMainBlockContainer").locator("[data-testid=stSelectbox]").first.click()
                page.get_by_role("option", name=args.spot).click()
                page.wait_for_selector(f"text=local time", timeout=60000)
                page.wait_for_timeout(2000)

            spot = (args.spot or "default").lower().replace(" ", "-")
            tab_names = page.get_by_role("tab").all_text_contents()   # read the tabs from the page itself
            for name in tab_names:
                page.get_by_role("tab", name=name).click()
                page.wait_for_timeout(2500)                           # let the charts draw
                slug = name.lower().replace("&", "and").replace(" ", "-")
                path = out / f"{spot}_{slug}{suffix}.png"
                page.screenshot(path=str(path), full_page=True)
                print("saved", path.relative_to(PROJECT))
            browser.close()
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
