import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def server():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def page(server):
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 800, "height": 520})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{server}/examples/web/index.html?seed=4")
        yield page
        assert errors == []
        browser.close()


def _landed_on(page, selector):
    page.wait_for_function(
        f"window.pet && window.pet.core.ledge && window.pet.core.ledge.key === document.querySelector('{selector}')"
        " && ['land', 'idle', 'walk'].includes(window.pet.core.mood)",
        timeout=5000,
    )


def test_the_pet_lands_on_the_button_under_it(page):
    _landed_on(page, "#save")
    assert page.evaluate("window.pet.core.y") == 300


def test_clicks_beside_the_pet_still_reach_the_page(page):
    _landed_on(page, "#save")
    page.click("#elsewhere")
    assert page.evaluate("window.clicks") == ["elsewhere"]


def test_a_press_on_the_pet_picks_it_up_and_a_drag_throws_it(page):
    _landed_on(page, "#save")
    page.evaluate("window.pet.core.mood = 'idle'; window.pet.core.timer = 60")
    box = page.locator("[data-desktop-pet=body]").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    assert page.evaluate("window.pet.core.mood") == "held"
    page.mouse.move(x + 60, y - 60, steps=3)
    page.mouse.move(x + 160, y - 160, steps=3)
    page.mouse.up()
    assert page.evaluate("window.pet.core.mood") == "air"
    assert page.evaluate("window.clicks") == [], "the press on the pet must not click the button under it"


def test_the_pet_is_drawn(page):
    _landed_on(page, "#save")
    painted = page.evaluate("""() => {
        const canvas = document.querySelector('[data-desktop-pet=sprite]');
        const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
        let count = 0;
        for (let i = 3; i < data.length; i += 4) if (data[i] > 0) count++;
        return count;
    }""")
    assert painted > 500
