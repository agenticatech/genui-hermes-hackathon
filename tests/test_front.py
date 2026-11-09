"""End to end, without Hermes: the agent's tools write and broadcast, the Desktop half's real code
(plugin/desktop/plugin.js, with the SDK and React replaced by stand-ins) builds the frame from the
backend payload, live events repaint it, and a click becomes the user turn the model receives.

show → 3 updates → click: the card is built once and repainted in place, and the composer gets
{"type": "user_action", "component_id": "pr", "action_id": "resolve_conflicts"}.
"""
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from library import Components, Store, component_key, frame_payload

PLUGIN = Path(__file__).resolve().parent.parent / "plugin"
ORIGIN = "http://genui.test"

# Stand-ins for the only modules Desktop lets plugin.js import. The composer is the boundary with
# the model: what submit() receives is the user turn Hermes sends to it.
FAKES = {
    "/sdk.js": """
export const host = {
  composer: { submit: (sessionId, text) => { window.__turns.push({ sessionId, text }); return window.__composerVisible } },
  notify: (n) => window.__notices.push(n),
}
export const SandboxedFrame = 'iframe'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const TRANSCRIPT_DIRECTIVE_AREA = 'transcript.directive'
""",
    "/react.js": """
export const useEffect = () => {}, useLayoutEffect = () => {}, useMemo = (f) => f(), useRef = (v) => ({ current: v }), useState = (v) => [v, () => {}]
""",
    "/jsx.js": "export const jsx = () => null\n",
}

HARNESS = """<!doctype html><html><head><meta charset="utf-8">
<script type="importmap">{"imports": {"@hermes/plugin-sdk": "/sdk.js", "react": "/react.js", "react/jsx-runtime": "/jsx.js"}}</script>
</head><body style="margin:0">
<div style="height:600px">earlier messages</div>
<iframe id="card" sandbox="allow-scripts" style="width:640px;height:600px;border:0"></iframe>
<script type="module">
import { host } from '@hermes/plugin-sdk'
import { ComponentChannel, frameDocument, toDataUrl } from '/plugin.js'
window.__turns = []; window.__notices = []; window.__composerVisible = true; window.__heights = []
const iframe = document.getElementById('card')
// Wired like GenuiComponent wires it.
const channel = new ComponentChannel({
  submit: (text) => host.composer.submit(null, text),
  notify: () => host.notify({ kind: 'warning' }),
  onResize: (h) => window.__heights.push(h),
})
addEventListener('message', (e) => channel.handle(e))
window.__load = (payload) => { channel.accept(payload); channel.attach(iframe.contentWindow); iframe.src = toDataUrl(frameDocument(payload)) }
window.__event = (payload) => channel.accept(payload)   // what ctx.onEvent('plugin.genui.component') hands over
window.__ready = true
</script></body></html>"""

PR = {
    "title": "Refresh sessions in the auth middleware", "pr": None, "status": "committing",
    "status_text": "Committing 4 changed files",
    "commits": [{"sha": "-", "message": "Uncommitted changes", "author": "You", "branch": "feat/session-refresh", "state": "pending"},
                {"sha": "c78a92", "message": "Refresh sessions near expiry", "author": "You", "age": "25m", "state": "ok"}],
}
UPDATES = [
    {"pr": 128, "status": "fetching", "status_text": "Fetching main"},
    {"status": "checking_merge", "status_text": "Checking it merges cleanly",
     "commits": [{"sha": "5be27d", "message": "Read sessions with the current key", "author": "Lena", "branch": "main", "state": "pending"},
                 {"sha": "c78a92", "message": "Refresh sessions near expiry", "author": "You", "age": "25m", "state": "ok"}]},
    {"status": "conflicts", "status_text": "3 conflicts with main", "conflicts": {"total": 3, "resolved": 0, "files": ["auth.ts", "middleware.ts"]},
     "explanation": "Lena's commits changed the same lines in auth.ts and middleware.ts. I can merge main in and resolve them.",
     "actions": [{"id": "resolve_conflicts", "label": "Resolve conflicts", "kind": "primary"}]},
]


@pytest.fixture
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))

        def serve(route):
            path = route.request.url.removeprefix(ORIGIN)
            if path == "/plugin.js":
                body = (PLUGIN / "desktop" / "plugin.js").read_text(encoding="utf-8")
            elif path in FAKES:
                body = FAKES[path]
            else:
                body = HARNESS
            route.fulfill(body=body, content_type="text/javascript" if path.endswith(".js") else "text/html")

        pg.route(f"{ORIGIN}/**", serve)
        pg.goto(f"{ORIGIN}/")
        pg.wait_for_function("window.__ready === true")
        pg.errors = errors
        yield pg
        browser.close()


@pytest.fixture
def agent(tmp_path):
    events = []
    comps = Components(Store(tmp_path), broadcast=lambda record: events.append(dict(record)))
    comps.events = events
    return comps


def card(page):
    return page.frame_locator("#card")


def test_show_three_updates_then_click_reaches_the_model(page, agent):
    assert agent.show("s1", {"id": "pr", "type": "pr_card", "props": PR})["ok"]
    record = agent.store.get(component_key("s1", "pr"))
    page.evaluate("p => window.__load(p)", frame_payload(record))   # the directive renders: GET /component/<key>
    status = card(page).locator(".gpr-status-text")
    status.wait_for()
    assert status.inner_text() == "Committing 4 changed files"
    frame = page.frames[1]
    frame.evaluate("() => { window.__sameDocument = true; document.querySelector('.gpr').__sameCard = true }")
    src = page.get_attribute("#card", "src")
    page.evaluate("() => window.scrollTo(0, 300)")

    for patch, expected in zip(UPDATES, ["Fetching main", "Checking it merges cleanly", "3 conflicts with main"]):
        assert agent.update("s1", {"id": "pr", "patch": patch}) == {"ok": True}
        page.evaluate("p => window.__event(p)", agent.events[-1])      # plugin.genui.component
        card(page).locator(".gpr-status-text", has_text=expected).wait_for()

    # Repainted in place: same document, same card node, same src, reader's scroll untouched.
    assert frame.evaluate("() => window.__sameDocument === true && document.querySelector('.gpr').__sameCard === true")
    assert page.get_attribute("#card", "src") == src
    assert page.evaluate("() => window.scrollY") == 300
    card(page).locator(".gpr-num", has_text="#128").wait_for()      # the PR number decodes into place
    assert card(page).locator(".gpr-row").count() == 2              # the commits array was replaced whole
    assert card(page).locator(".gpr-target .gpr-who").inner_text() == "3 conflicts"   # the merge into main

    # A stale event (an older rev arriving late) changes nothing.
    page.evaluate("p => window.__event(p)", agent.events[1])
    assert card(page).locator(".gpr-status-text").inner_text() == "3 conflicts with main"

    button = card(page).locator('[data-action="resolve_conflicts"]')
    button.click()
    page.wait_for_function("() => window.__turns.length === 1")    # frame → host is a postMessage
    turns = page.evaluate("() => window.__turns")
    assert turns[0]["sessionId"] is None                            # the chat the user is looking at
    assert json.loads(turns[0]["text"]) == {"type": "user_action", "component_id": "pr", "action_id": "resolve_conflicts"}
    assert button.is_disabled()                                     # one click, one decision
    button.click(force=True)
    page.wait_for_timeout(100)
    assert len(page.evaluate("() => window.__turns")) == 1
    assert page.errors == []


def test_undelivered_click_can_be_retried(page, agent):
    agent.show("s1", {"id": "pr", "type": "pr_card", "props": {**PR, **UPDATES[2], "status": "conflicts"}})
    page.evaluate("p => window.__load(p)", frame_payload(agent.store.get(component_key("s1", "pr"))))
    page.evaluate("() => { window.__composerVisible = false }")    # the chat is not on screen
    button = card(page).locator('[data-action="resolve_conflicts"]')
    button.click()
    page.wait_for_function("() => window.__notices.length === 1")   # the user is told why
    page.frames[1].wait_for_function("() => !document.querySelector('[data-action=resolve_conflicts]').disabled")
    page.evaluate("() => { window.__composerVisible = true }")
    button.click()
    page.wait_for_function("() => window.__turns.length === 2")     # both attempts reached submit()
    assert page.errors == []


def test_the_users_selection_reaches_the_model(page, agent):
    files = [{"id": f, "label": f, "size_mb": mb, "selected": True} for f, mb in
             [("backup.zip", 11200), ("ubuntu.iso", 5800), ("talk.mp4", 2300)]]
    files.append({"id": "invoice.pdf", "label": "invoice.pdf", "size_mb": 0.4, "locked": True, "tag": "open"})
    agent.show("s1", {"id": "downloads", "type": "review_list", "props": {
        "title": "Free up space", "status": "review", "items": files, "summary": {"total_mb": 19300.4},
        "actions": [{"id": "delete_selected", "label": "Delete selected", "kind": "danger"}]}})
    page.evaluate("p => window.__load(p)", frame_payload(agent.store.get(component_key("s1", "downloads"))))
    rows = card(page).locator('[data-field="selected"]')
    rows.first.wait_for()
    assert rows.count() == 4 and card(page).locator('[data-field="selected"][value="invoice.pdf"]').is_disabled()
    card(page).locator('[data-field="selected"][value="talk.mp4"]').uncheck()      # the user disagrees with one pick
    assert "2 selected" in card(page).locator(".grl-picked").inner_text()

    # An unrelated repaint (a newer rev with the same items) keeps the user's ticks.
    agent.update("s1", {"id": "downloads", "patch": {"status_text": "Pick what to delete"}})
    page.evaluate("p => window.__event(p)", agent.events[-1])
    card(page).locator(".grl-status-text", has_text="Pick what to delete").wait_for()
    assert not card(page).locator('[data-field="selected"][value="talk.mp4"]').is_checked()

    card(page).locator('[data-action="delete_selected"]').click()
    page.wait_for_function("() => window.__turns.length === 1")
    turn = json.loads(page.evaluate("() => window.__turns[0].text"))
    assert turn == {"type": "user_action", "component_id": "downloads", "action_id": "delete_selected",
                    "values": {"selected": ["backup.zip", "ubuntu.iso"]}}
    assert page.errors == []


def test_frame_reports_its_height(page, agent):
    agent.show("s1", {"id": "pr", "type": "pr_card", "props": PR})
    page.evaluate("p => window.__load(p)", frame_payload(agent.store.get(component_key("s1", "pr"))))
    page.wait_for_function("() => window.__heights.length > 0")
    page.wait_for_timeout(1500)                                     # the card builds itself, then settles
    heights = page.evaluate("() => window.__heights")
    before = heights[-1]
    assert 100 < before < 400
    assert len(set(heights)) > 3                                    # the frame followed the card as it grew
    agent.update("s1", {"id": "pr", "patch": UPDATES[2]})
    page.evaluate("p => window.__event(p)", agent.events[-1])
    page.wait_for_function(f"() => window.__heights.at(-1) > {before}")
