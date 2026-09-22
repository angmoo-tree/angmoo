"""Read-only local browser verification; never starts a character activity."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument("--world", required=True)
parser.add_argument("--characters", nargs="+", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
evidence = root / "docs/architecture/evidence"
evidence.mkdir(parents=True, exist_ok=True)
screenshots = root.parent / "docs/handoff/evidence/09-22-feed-readiness"
screenshots.mkdir(parents=True, exist_ok=True)
records, mutations, read_preflights = [], [], []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    def inspect_request(request):
        path = request.url.split("?")[0]
        if request.method in {"GET", "HEAD", "OPTIONS"} or "/api/backend/" not in path or "/auth/" in path:
            return
        if request.method == "POST" and path.endswith("/autonomy-setup/preflight"):
            # Existing setup screen quotes readiness with POST; service is read-only.
            read_preflights.append(1)
        else:
            mutations.append(path)
    page.on("request", inspect_request)
    for index, character in enumerate(args.characters):
        for surface, path in [("topics", f"/agents/{character}?tab=settings"),
            ("setup", f"/characters/{character}/worlds/{args.world}/autonomy-setup")]:
            received = []
            def capture(response):
                if "recommendation-topics" in response.url or response.url.endswith("/feed-status"):
                    body = response.json()
                    if isinstance(body, dict) and body.get("feed_status"):
                        received.append(body["feed_status"])
            page.on("response", capture)
            page.goto("http://127.0.0.1:3000" + path, wait_until="networkidle", timeout=60000)
            panel = page.get_by_role("region", name="Feed 실행 상태", exact=True)
            expect(panel).to_be_visible(timeout=30000)
            if surface == "topics":
                page.get_by_role("button", name="상태 새로고침", exact=True).click()
                expect(panel).to_be_visible()
            else:
                expect(page.get_by_text("다음 검색 묶음", exact=True)).to_have_count(0)
            page.reload(wait_until="networkidle")
            expect(panel).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("body").evaluate('(e)=>e.style.zoom="2"')
            panel.scroll_into_view_if_needed()
            assert panel.evaluate("e=>e.scrollWidth <= e.clientWidth")
            page.keyboard.press("Tab")
            panel.screenshot(path=str(screenshots / f"{index}-{surface}-200pct.png"))
            assert received
            latest = received[-1]
            records.append({"character_index": index, "surface": surface,
                "readiness": latest["readiness"]["state"], "persona_changed": latest["readiness"]["persona_changed"],
                "last_attempt_present": latest["last_attempt"] is not None,
                "read_count": len(received), "narrow_200pct": True})
            page.remove_listener("response", capture)
            page.locator("body").evaluate('(e)=>e.style.zoom="1"')
            page.set_viewport_size({"width": 1440, "height": 1000})
    browser.close()
assert not mutations, "Unexpected non-GET routes: " + str(mutations)
result = {"delegated_ui_check": True, "triggered_ai_calls": 0, "mutation_count": len(mutations), "existing_read_only_preflight_posts": len(read_preflights), "results": records}
(evidence / "feed-readiness-local-ui.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
