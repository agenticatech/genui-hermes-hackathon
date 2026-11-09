// The default theme's card kit (GenUICard): what every default card shares, so task_card and
// review_list read as one family with pr_card. A card is a shell (header with a state badge, a body
// the component fills, an explanation, a footer with the live status line and one pill), plus the
// spine: a column of nodes joined by a line that fills as steps are reached, with an optional side
// branch (a rollback) that forks off a failed node. library.frame_payload loads this file ahead of
// the component's theme; it draws nothing on its own.
(() => {
if (window.GenUICard) return;
const M = window.GenUIMotion;
const arr = (v) => (Array.isArray(v) ? v : []);
const str = (v) => (v === undefined || v === null ? "" : String(v));

const ICONS = {
  ok: '<svg viewBox="0 0 12 12"><path d="M2.6 6.3l2.2 2.2 4.6-4.9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  bad: '<svg viewBox="0 0 12 12"><path d="M3.2 3.2l5.6 5.6M8.8 3.2l-5.6 5.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  warn: '<svg viewBox="0 0 12 12"><path d="M6 1.7l4.5 8H1.5z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M6 4.9v2.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="6" cy="8.35" r=".7" fill="currentColor"/></svg>',
  wait: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"><circle cx="6" cy="6" r="4.6"/><path d="M6 3.4V6l1.7 1.1"/></svg>',
  lock: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2.6" y="5.2" width="6.8" height="4.8" rx="1.2"/><path d="M4.2 5.2V3.9a1.8 1.8 0 013.6 0v1.3"/></svg>',
  link: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><path d="M4.5 2.5h5v5M9.5 2.5L3 9"/></svg>',
  github: '<svg viewBox="0 0 16 16"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>',
};

// "Deploy 2.4.0 to production" → "Deploying": what a decision's pill says while the agent carries it
// out, unless the action names it (busy_label).
const busyLabel = (a) => {
  if (a.busy_label) return str(a.busy_label);
  const w = (str(a.label || a.id).trim().split(/\s+/)[0] || "Work").toLowerCase();
  const ing = { stop: "stopping", run: "running", set: "setting", ship: "shipping", drop: "dropping", plan: "planning" }[w]
    || (w.endsWith("ing") ? w : /[^aeiou]e$/.test(w) ? `${w.slice(0, -1)}ing` : `${w}ing`);
  return ing[0].toUpperCase() + ing.slice(1);
};

const maker = (doc) => (tag, cls, parent) => {
  const n = doc.createElement(tag);
  if (cls) n.className = cls;
  if (parent) parent.append(n);
  return n;
};

// The shell. `prefix` names the component's own classes (gtk, grl): the card carries it, and the
// status line is also `<prefix>-status-text`, so tests and themes can find it by name.
function shell(root, prefix) {
  const doc = root.ownerDocument;
  if (!doc.getElementById("gc-style")) {
    const style = doc.createElement("style");
    style.id = "gc-style";
    style.textContent = CSS;
    doc.head.append(style);
  }
  const el = maker(doc);
  const card = el("article", `gc ${prefix}`);
  const hd = el("header", "gc-hd", card);
  const title = el("span", "gc-title", hd);
  const ui = { el, card, hd, first: true, name: el("b", "gc-name", title), badge: el("span", "gc-badge", hd) };
  ui.badgeText = el("span", "", ui.badge);
  ui.badge.hidden = true;
  ui.sub = el("div", "gc-sub", card);
  ui.sub.hidden = true;
  ui.body = el("div", "gc-body", card);
  ui.ex = el("p", "gc-ex", card);
  ui.ex.hidden = true;
  ui.ft = el("footer", "gc-ft", card);
  ui.status = el("span", "gc-status", ui.ft);
  ui.icon = el("span", "gc-icon", ui.status);
  ui.statusText = el("span", `gc-status-text ${prefix}-status-text`, ui.status);
  ui.acts = el("span", "gc-acts", ui.ft);
  ui.pop = M.popover(card, "gc-pop");
  root.replaceChildren(card);
  return ui;
}

// Title (decodes when it changes), one line of context, the state badge.
function header(ui, { title, sub, badge }) {
  const first = ui.first;
  (first ? M.setText : M.decode)(ui.name, title);
  const s = str(sub);
  if (s && ui.sub.textContent !== s) { if (first || ui.sub.hidden) M.setText(ui.sub, s); else M.decode(ui.sub, s); }
  if (first) ui.sub.hidden = !s; else M.toggle(ui.sub, !!s);
  const [tone, label] = badge || ["", ""];
  ui.badge.dataset.tone = tone;
  if (label && ui.badge.hidden) { ui.badge.hidden = false; if (!first) M.fade(ui.badge, { y: 0, scale: 0.9 }); }
  if (!label) ui.badge.hidden = true;
  if (first) M.setText(ui.badgeText, label); else M.roll(ui.badgeText, label);
}

// The live status line: an icon (spin, warn, wait, ok, bad, idle), the text with a shimmer while
// busy, and optionally one phrase in it that opens details on hover (hot: {re, render}).
function status(ui, { kind, text, busy, hot }) {
  const first = ui.first;
  ui.status.dataset.state = kind;
  if (ui.icon.dataset.kind !== kind) {
    ui.icon.dataset.kind = kind;
    ui.icon.innerHTML = ICONS[kind] || "";
    if (!first) M.fade(ui.icon, { y: 0, scale: 0.6, duration: 240 });
  }
  const t = str(text);
  const match = hot && hot.re ? hot.re.exec(t) : null;
  const key = `${t}|${match ? match[0] : ""}`;
  if (ui.statusText.__key !== key) {
    ui.statusText.__key = key;
    if (match) {
      const span = ui.el("span", "gc-hot");
      span.textContent = match[0];
      ui.statusText.replaceChildren(t.slice(0, match.index), span, t.slice(match.index + match[0].length));
      ui.pop.bind(span, hot.render);
    } else ui.statusText.textContent = t;
    if (!first) M.run(ui.statusText, [{ opacity: 0, transform: "translateY(55%)" }, { opacity: 1, transform: "none" }], { duration: 300 });
  }
  ui.statusText.classList.toggle("gu-shimmer", !!busy);
}

// The pill: the decision; once clicked, its own busy state until the agent answers; the next
// decision takes the same pill; links (where the result lives) when nothing is left to decide.
// values(), when given, adds what the card holds to the click (a quiz's answers).
function pills(ui, { actions, links, busy, emit, values }) {
  const first = ui.first, el = ui.el;
  ui.pillValues = values;
  actions = arr(actions).filter((a) => a && a.id);
  if (actions.length && ui.clicked && !actions.some((a) => a.id === ui.clicked)) ui.clicked = null;
  const items = [];
  if (actions.length) actions.forEach((a) => items.push({ kind: "action", key: `a:${a.id}`, a }));
  else if (busy && ui.clicked) items.push({ kind: "busy", key: `a:${ui.clicked}` });
  else arr(links).filter((l) => l && l.url).forEach((l) => items.push({ kind: "link", key: `l:${l.url}`, l }));
  if (!busy && !actions.length) ui.clicked = null;
  M.keyed(ui.acts, items, {
    key: (x) => x.key,
    adopt: (node, x) => x.kind === "action" && node.tagName === "BUTTON",
    create: (x) => {
      if (x.kind === "link") {
        const a = el("a", "gc-pill");
        el("span", "gc-pill-icon", a);
        el("span", "gc-lbl", a);
        return a;
      }
      const b = el("button", "gc-pill gc-btn");
      b.type = "button";
      el("span", "gc-pill-icon", b);
      el("span", "gc-spin", b);
      el("span", "gc-lbl", b);
      el("span", "gc-busy", b);
      b.addEventListener("click", () => {
        if (b.disabled) return;
        const id = str((b.__action || {}).id);
        ui.clicked = id;
        // One click, one decision: the pill becomes its busy state until the agent answers.
        M.resize(b, () => { b.disabled = true; }, { axis: "width", duration: 260 });
        emit(id, ui.pillValues ? ui.pillValues() : undefined);
      });
      return b;
    },
    update: (n, x, { adopted }) => {
      const icon = n.querySelector(".gc-pill-icon"), lbl = n.querySelector(".gc-lbl");
      if (x.kind === "link") {
        const gh = /github\.com/i.test(x.l.url);
        n.dataset.kind = "link";
        icon.innerHTML = gh ? ICONS.github : ICONS.link;
        M.setText(lbl, x.l.label || x.l.url);
        if (/^https?:\/\//i.test(str(x.l.url))) { n.href = x.l.url; n.target = "_blank"; n.rel = "noopener noreferrer"; }
        else n.removeAttribute("href");
        return;
      }
      if (x.kind !== "action") return;
      const a = x.a, prevId = n.dataset.action;
      n.__action = a;
      n.dataset.action = str(a.id);
      n.dataset.kind = ["primary", "secondary", "danger"].includes(a.kind) ? a.kind : "primary";
      M.setText(n.querySelector(".gc-busy"), busyLabel(a));
      if (adopted && prevId !== a.id) {
        M.resize(n, () => { n.disabled = false; M.setText(lbl, a.label || a.id); }, { axis: "width", duration: 300 });
        M.run(lbl, [{ opacity: 0, transform: "translateY(55%)" }, { opacity: 1, transform: "none" }], { duration: 300 });
      } else M.setText(lbl, a.label || a.id);
    },
    enter: (n) => { if (!first) M.fade(n, { y: 0, scale: 0.9, duration: 280 }); },
    exit: (n) => M.exit(n, { duration: 200 }),
  });
}

function explain(ui, text) {
  const ex = str(text);
  if (ex && ui.ex.textContent !== ex) { ui.ex.textContent = ex; if (!ui.first && !ui.ex.hidden) M.fade(ui.ex, { y: 2 }); }
  if (ui.first) ui.ex.hidden = !ex; else M.toggle(ui.ex, !!ex);
}

// Node kinds: ring (not reached), spin (working), wait (needs the user), dot (reached), ok, bad,
// warn, lock. A change of kind pops the new one in.
function node(n, kind, first) {
  if (n.dataset.kind === kind) return;
  const had = n.dataset.kind;
  n.dataset.kind = kind;
  n.innerHTML = kind === "ok" ? ICONS.ok : kind === "bad" ? ICONS.bad : kind === "warn" ? "!" : "";
  if (had && !first) M.run(n, [{ transform: "translate(-50%,-50%) scale(.4)", opacity: 0.2 }, { transform: "translate(-50%,-50%) scale(1)", opacity: 1 }], { duration: 300 });
}

// The spine: rows on lane 0 (the plan) or lane 1 (a branch forking off row `from`). Each row draws
// its own cell (an SVG as tall as the row), so rows that grow in stretch the line with them. A
// stretch of line is "on" once the row it leads to is reached, dashed and faint before that.
const LANE_X = [9, 21];
function spine(rows) {
  const segs = rows.map(() => []);
  const v = (r, lane, y0, y1, on) => segs[r].push(`<path class="l${lane} ${on ? "on" : "off"}" d="M${LANE_X[lane]} ${y0}V${y1}"/>`);
  const c = (r, a, y0, b, y1, lane, on) => {
    const ym = (y0 + y1) / 2;
    segs[r].push(`<path class="l${lane} ${on ? "on" : "off"}" d="M${LANE_X[a]} ${y0}C${LANE_X[a]} ${ym} ${LANE_X[b]} ${ym} ${LANE_X[b]} ${y1}"/>`);
  };
  const link = (idx, lane) => {
    for (let k = 0; k + 1 < idx.length; k++) {
      const i = idx[k], j = idx[k + 1], on = rows[j].reached;
      v(i, lane, 50, 100, on);
      for (let r = i + 1; r < j; r++) v(r, lane, 0, 100, on);
      v(j, lane, 0, 50, on);
    }
  };
  link(rows.map((r, i) => (r.lane === 0 ? i : -1)).filter((i) => i >= 0), 0);
  const side = rows.map((r, i) => (r.lane === 1 ? i : -1)).filter((i) => i >= 0);
  if (side.length) {
    const from = rows[side[0]].from ?? -1, first = side[0], on = rows[first].reached;
    if (from >= 0 && from < first) {
      c(from, 0, 50, 1, 100, 1, on);
      for (let r = from + 1; r < first; r++) v(r, 1, 0, 100, on);
      v(first, 1, 0, 50, on);
    }
    link(side, 1);
  }
  return segs.map((s) => s.join(""));
}

// A spine row: cell (svg + node), main (text, chip, underline), meta. Themes add their own parts.
function spineRow(el) {
  const row = el("div", "gc-r");
  const lanes = el("span", "gc-lanes", row);
  lanes.innerHTML = '<svg viewBox="0 0 30 100" preserveAspectRatio="none" aria-hidden="true"></svg>';
  el("span", "gc-node", lanes);
  const main = el("span", "gc-main", row);
  const tw = el("span", "gc-tw", main);
  el("span", "gc-text", tw);
  el("i", "gc-under", tw);
  el("span", "gc-meta", row);
  return row;
}
function paintSpineRow(row, { svg, lane, kind, first, index }) {
  const [lanes] = row.children;
  const [s, n] = lanes.children;
  if (s.__d !== svg) { s.innerHTML = svg; s.__d = svg; }
  n.style.left = `${LANE_X[lane]}px`;
  row.dataset.lane = lane;
  row.style.setProperty("--d", `${index * 60}ms`);
  node(n, kind, first);
}

// First paint: the card builds itself. The header lands, the body's rows arrive one after another
// (from the bottom for a history, from the top for a plan) while the card grows to fit, then the
// status line.
function build(ui, rows, { fromBottom = false } = {}) {
  const card = ui.card;
  const full = card.getBoundingClientRect().height;
  const head = ui.hd.getBoundingClientRect().bottom - card.getBoundingClientRect().top + 6;
  const span = 140 + rows.length * 45;
  M.run(card, [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 300 });
  if (full > head) {
    card.style.overflow = "hidden";
    const grow = M.run(card, [{ height: `${head}px` }, { height: `${full}px` }], { duration: span + 220 });
    if (grow) grow.finished.then(() => { card.style.overflow = ""; }, () => {}); else card.style.overflow = "";
  }
  rows.forEach((r, i) => M.fade(r, { delay: 110 + (fromBottom ? rows.length - 1 - i : i) * 45, duration: 320, y: 5 }));
  M.fade(ui.ft, { delay: span + 40, duration: 300 });
  M.fade(ui.ex, { delay: span, duration: 300 });
}

// A figure's tone and an optional "x / y" gauge under it.
const ratio = (value) => {
  const m = /(-?\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/.exec(str(value));
  return m && Number(m[2]) > 0 ? Math.max(0, Math.min(1, Number(m[1]) / Number(m[2]))) : null;
};

const CSS = `
@property --gc-on { syntax: '<color>'; inherits: true; initial-value: transparent; }
@property --gc-side { syntax: '<color>'; inherits: true; initial-value: transparent; }
.gc {
  --gc-fg: var(--foreground, #1f2328);
  --gc-dim: var(--muted-foreground, #7d858f);
  --gc-line: var(--border, color-mix(in srgb, var(--gc-fg) 12%, transparent));
  --gc-accent: var(--accent, #2f6fe4);
  --gc-ok: #2f9a5f; --gc-warn: #d2801a; --gc-bad: #d04a3c;
  --gc-flash: color-mix(in srgb, var(--gc-accent) 13%, transparent);
  --gc-mono: var(--host-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
  --gc-on: var(--gc-accent); --gc-side: var(--gc-warn);
  --gu-shimmer-base: var(--gc-dim); --gu-shimmer-hi: var(--gc-fg);
  position: relative; box-sizing: border-box; padding: 11px 14px 10px;
  border: 1px solid var(--gc-line); border-radius: 12px; background: var(--card, transparent);
  box-shadow: 0 1px 2px color-mix(in srgb, #000 4%, transparent);
  color: var(--gc-fg); font: 13px/1.45 var(--host-font, system-ui, -apple-system, "Segoe UI", sans-serif);
}
.gc[data-end=ok] { --gc-on: var(--gc-ok); }
.gc *, .gc *::before, .gc *::after { box-sizing: border-box; }
.gc [hidden] { display: none !important; }
.gc-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.gc-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gc-name { font-weight: 600; }
.gc-badge { flex: none; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; color: var(--gc-dim); transition: color .4s; }
.gc-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.gc-badge[data-tone=ok] { color: var(--gc-ok); }
.gc-badge[data-tone=warn] { color: var(--gc-warn); }
.gc-badge[data-tone=bad] { color: var(--gc-bad); }
.gc-badge[data-tone=busy] { color: var(--gc-accent); }
.gc-sub { color: var(--gc-dim); font-size: 12px; margin-top: 1px; }
.gc-body { margin-top: 7px; }
.gc-ex { margin: 9px 0 0; color: var(--gc-dim); font-size: 12.5px; }

.gc-r { position: relative; display: grid; grid-template-columns: 30px minmax(0, 1fr) auto; align-items: center; column-gap: 4px;
  min-height: 24px; padding-right: 4px; border-radius: 6px; color: var(--gc-fg);
  transition: --gc-on .5s ease var(--d, 0ms), --gc-side .5s ease var(--d, 0ms), color .45s, background-color .3s; }
.gc-r[data-tone=dim] { color: var(--gc-dim); }
.gc-r[data-tone=bad] { color: var(--gc-bad); }
.gc-r[data-tone=warn] { color: var(--gc-warn); }
.gc-lanes { position: relative; align-self: stretch; }
.gc-lanes svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.gc-lanes path { fill: none; stroke-width: 1.5; vector-effect: non-scaling-stroke; stroke-linecap: round; }
.gc-lanes path.l0.on { stroke: var(--gc-on); }
.gc-lanes path.l1.on { stroke: var(--gc-side); }
.gc-lanes path.off { stroke: color-mix(in srgb, var(--gc-fg) 22%, transparent); stroke-dasharray: 2.5 3; }
.gc-node { position: absolute; top: 50%; width: 7px; height: 7px; border-radius: 50%; transform: translate(-50%, -50%);
  display: grid; place-items: center; background: var(--gc-on); color: #fff; font: 700 8.5px/1 var(--host-font, system-ui, sans-serif);
  transition: background-color .4s, box-shadow .4s; }
.gc-r[data-lane="1"] .gc-node { background: var(--gc-side); }
.gc-node svg { width: 8px; height: 8px; }
.gc-node[data-kind=ring] { width: 9px; height: 9px; background: var(--card, #fff) !important; box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--gc-fg) 30%, transparent); }
.gc-node[data-kind=spin] { width: 10px; height: 10px; background: transparent !important; border: 1.5px solid color-mix(in srgb, var(--gc-dim) 35%, transparent);
  border-top-color: var(--gc-fg); animation: gc-node-spin .75s linear infinite; }
.gc-node[data-kind=wait] { width: 9px; height: 9px; background: var(--card, #fff) !important; box-shadow: inset 0 0 0 1.5px var(--gc-warn); }
.gc-node[data-kind=wait]::after { content: ""; position: absolute; inset: -4px; border-radius: 50%; border: 1.5px solid var(--gc-warn); animation: gc-pulse 1.4s ease-out infinite; }
.gc-node[data-kind=ok] { width: 13px; height: 13px; background: var(--gc-ok) !important; }
.gc-node[data-kind=bad] { width: 13px; height: 13px; background: var(--gc-bad) !important; }
.gc-node[data-kind=warn] { width: 13px; height: 13px; background: var(--gc-warn) !important; }
.gc-node[data-kind=skip] { width: 7px; height: 7px; background: color-mix(in srgb, var(--gc-fg) 22%, transparent) !important; }
.gc-main { min-width: 0; display: flex; align-items: center; gap: 6px; overflow: hidden; white-space: nowrap; }
.gc-tw { position: relative; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.gc-under { position: absolute; left: 0; bottom: 1px; height: 1.5px; border-radius: 1px; background: var(--gc-on); width: 0;
  transition: width .6s cubic-bezier(.2,.75,.15,1); }
.gc-meta { justify-self: end; display: inline-flex; gap: 7px; color: var(--gc-dim); font: 11px var(--gc-mono); white-space: nowrap; }
.gc-meta[data-tone=bad] { color: var(--gc-bad); }
.gc-meta[data-tone=ok] { color: var(--gc-ok); }
.gc-meta[data-tone=count] { color: var(--gc-fg); }
.gc-strike { background: linear-gradient(currentColor, currentColor) 0 58% / 0% 1px no-repeat; transition: background-size .5s cubic-bezier(.2,.75,.15,1) var(--sd, 0ms); }
.gc-strike.is-on { background-size: 100% 1px; }
.gc-tag { flex: none; padding: 0 6px; border-radius: 999px; font: 11px/17px var(--host-font, system-ui, sans-serif);
  color: var(--gc-dim); background: color-mix(in srgb, var(--gc-fg) 7%, transparent); }
.gc-tag[data-tone=warn] { color: var(--gc-warn); background: color-mix(in srgb, var(--gc-warn) 12%, transparent); }
.gc-tag[data-tone=bad] { color: var(--gc-bad); background: color-mix(in srgb, var(--gc-bad) 11%, transparent); }
.gc-tag[data-tone=good] { color: var(--gc-ok); background: color-mix(in srgb, var(--gc-ok) 11%, transparent); }

.gc-ft { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 26px; margin-top: 8px; }
.gc-status { min-width: 0; display: inline-flex; align-items: center; gap: 7px; }
.gc-icon { flex: none; display: grid; place-items: center; width: 12px; height: 12px; color: var(--gc-dim); }
.gc-icon svg { width: 12px; height: 12px; }
.gc-status[data-state=spin] .gc-icon { width: 11px; height: 11px; border-radius: 50%; border: 1.5px solid color-mix(in srgb, var(--gc-dim) 35%, transparent);
  border-top-color: var(--gc-fg); animation: gc-spin .75s linear infinite; }
.gc-status[data-state=warn] .gc-icon, .gc-status[data-state=wait] .gc-icon { color: var(--gc-warn); }
.gc-status[data-state=ok] .gc-icon { color: var(--gc-ok); }
.gc-status[data-state=bad] .gc-icon { color: var(--gc-bad); }
.gc-status-text { display: inline-block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gc-hot { text-decoration: underline dotted; text-decoration-thickness: 1px; text-underline-offset: 3px; cursor: default; }
.gc-acts { flex: none; display: inline-flex; gap: 6px; }
.gc-pill { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 26px; padding: 0 12px; border-radius: 999px;
  font: 500 12.5px/1 var(--host-font, system-ui, sans-serif); white-space: nowrap; overflow: hidden; text-decoration: none; border: 0; cursor: pointer;
  color: var(--gc-accent); background: color-mix(in srgb, var(--gc-accent) 12%, transparent); transition: background-color .25s, color .25s, transform .12s; }
.gc-pill:hover:not(:disabled) { background: color-mix(in srgb, var(--gc-accent) 19%, transparent); }
.gc-pill:active:not(:disabled) { transform: scale(.97); }
.gc-pill:focus-visible { outline: 2px solid var(--gc-accent); outline-offset: 2px; }
.gc-pill[data-kind=secondary] { color: var(--gc-fg); background: color-mix(in srgb, var(--gc-fg) 7%, transparent); }
.gc-pill[data-kind=danger] { color: var(--gc-bad); background: color-mix(in srgb, var(--gc-bad) 11%, transparent); }
.gc-pill[data-kind=danger]:hover:not(:disabled) { background: color-mix(in srgb, var(--gc-bad) 17%, transparent); }
.gc-pill[data-kind=link] { color: var(--gc-fg); background: color-mix(in srgb, var(--gc-fg) 6%, transparent); }
.gc-pill-icon { display: grid; place-items: center; }
.gc-pill-icon:empty { display: none; }
.gc-pill-icon svg { width: 12px; height: 12px; }
.gc-spin, .gc-busy { display: none; }
.gc-btn:disabled { cursor: default; color: var(--gc-dim); background: color-mix(in srgb, var(--gc-fg) 6%, transparent); }
.gc-btn:disabled .gc-lbl, .gc-btn:disabled .gc-pill-icon { display: none; }
.gc-btn:disabled .gc-busy { display: inline; }
.gc-btn:disabled .gc-spin { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 1.5px solid color-mix(in srgb, var(--gc-dim) 35%, transparent); border-top-color: var(--gc-fg); animation: gc-spin .75s linear infinite; }

.gc-pop { padding: 8px 10px; border-radius: 10px; border: 1px solid var(--gc-line); background: var(--card, #fff);
  box-shadow: 0 10px 28px color-mix(in srgb, #000 14%, transparent), 0 1px 3px color-mix(in srgb, #000 6%, transparent);
  color: var(--gc-fg); font-size: 12px; line-height: 1.45; white-space: nowrap; }
.gc-pop-hd { color: var(--gc-dim); padding-bottom: 5px; margin-bottom: 5px; border-bottom: 1px solid var(--gc-line); }
.gc-pop-hd b { color: var(--gc-fg); font-weight: 600; }
.gc-pop-log { margin: 0; font: 11px/1.6 var(--gc-mono); color: var(--gc-dim); }
.gc-pop-log b { color: var(--gc-fg); font-weight: 400; }
.gc-pop-row { display: flex; justify-content: space-between; gap: 14px; font: 11px/1.7 var(--gc-mono); }
.gc-pop-row span:last-child { color: var(--gc-dim); }

@keyframes gc-spin { to { transform: rotate(360deg); } }
@keyframes gc-node-spin { from { transform: translate(-50%, -50%) rotate(0); } to { transform: translate(-50%, -50%) rotate(360deg); } }
@keyframes gc-pulse { from { opacity: .7; transform: scale(.6); } to { opacity: 0; transform: scale(1.5); } }
@media (prefers-reduced-motion: reduce) {
  .gc, .gc * { animation-duration: 1ms !important; animation-iteration-count: 1 !important; transition: none !important; }
}
`;

window.GenUICard = Object.freeze({ ICONS, arr, str, busyLabel, shell, header, status, pills, explain, node, spine, spineRow, paintSpineRow, build, ratio, LANE_X });
})();
