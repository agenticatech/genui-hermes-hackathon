"""Simulated user for v3. It only reacts when the agent ends its turn: it may fill the component's
fields, then click one offered action.

task["user_simulator"]["scripted"]["clicks"]: ordered steps, each either a regex or an object
  {"click": "<regex>", "set": {"<field>": ["<regex>", ...] | <value>}}
The user takes the first visible, enabled action whose id or label matches the first step not used
yet; before clicking, it sets the step's fields: a list picks, among the field's checkboxes, those
whose value or row text matches one of the regexes (and unticks the others); a scalar fills a
range, number, text or select field. Anything else on screen is ignored.
"""
from __future__ import annotations

import re


class ScriptedUser:
    def __init__(self, task: dict):
        cfg = task.get("user_simulator", {}).get("scripted", {})
        self.pending = [s if isinstance(s, dict) else {"click": s} for s in cfg.get("clicks", [])]
        self.text_reply = cfg.get("text_reply", "Yes, go ahead.")

    def _fill(self, card, fields: dict) -> None:
        for name, want in fields.items():
            inputs = card.locator(f'[data-field="{name}"]')
            for i in range(inputs.count()):
                el = inputs.nth(i)
                kind = (el.get_attribute("type") or el.evaluate("e => e.tagName")).lower()
                if kind == "checkbox":
                    if not el.is_enabled():
                        continue
                    row = el.evaluate("e => (e.closest('label, [data-row], li, tr') || e.parentElement).innerText")
                    value = el.get_attribute("value") or ""
                    hit = any(re.search(rx, value, re.I) or re.search(rx, row, re.I) for rx in want)
                    el.set_checked(hit)
                elif kind == "select":
                    el.select_option(str(want))
                else:
                    el.fill(str(want))
                    el.dispatch_event("input")
                    el.dispatch_event("change")

    def act(self, ep) -> str | None:
        buttons = ep.page.locator("[data-cid] [data-action]")
        offered = []
        for i in range(buttons.count()):
            b = buttons.nth(i)
            if b.is_visible() and b.is_enabled():
                offered.append((b, b.get_attribute("data-action") or "", b.inner_text().strip()))
        for step in list(self.pending):
            for b, aid, label in offered:
                if re.search(step["click"], aid, re.I) or re.search(step["click"], label, re.I):
                    self.pending.remove(step)
                    if step.get("set"):
                        self._fill(b.locator("xpath=ancestor::*[@data-cid][1]"), step["set"])
                    b.click()
                    ep.page.wait_for_timeout(30)
                    return label
        return None

    def reply(self, question: str) -> str:
        return self.text_reply
