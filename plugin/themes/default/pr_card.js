// Default theme for pr_card. A theme only draws props: emit(action_id) hands a decision back to the
// agent, and nothing else leaves the card. Every paint after the first keeps the same nodes and
// changes only what differs (rows keyed by sha, checks by name, pills by id), and every difference
// is shown as motion: rows open a gap and grow in, a pending row decodes into the commit it became,
// conflict badges turn into checks, the action pill turns into its own busy state, and on merge the
// colour runs down the graph. GenUI.motion (motion.js) provides the moves.
// Colours and fonts come from the host (--foreground, --muted-foreground, --accent, --border,
// --card, --host-font, --host-mono, set by the Desktop half), with fallbacks for a bare page.
// Wrapped in a function: themes share one global scope in some hosts, so nothing may leak a name.
(() => {
const M = GenUI.motion;
const BUSY = new Set(["committing", "pushing", "opening_pr", "fetching", "checking_merge", "resolving",
  "pushing_merge", "checks_running", "merging"]);
const STATUS_TEXT = {
  committing: "Committing", pushing: "Pushing", opening_pr: "Opening the pull request", fetching: "Fetching main",
  checking_merge: "Checking it merges cleanly", conflicts: "Conflicts with main", resolving: "Resolving conflicts",
  pushing_merge: "Pushing the merge", checks_running: "Running checks", ready: "Ready to merge", merging: "Merging",
  merged: "Merged", failed: "Failed",
};
const LANE_X = [7, 19, 31]; // graph lanes: the base branch, this PR's branch, any other branch
const arr = (v) => (Array.isArray(v) ? v : []);
const str = (v) => (v === undefined || v === null ? "" : String(v));
const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const ICONS = {
  ok: '<svg viewBox="0 0 12 12"><path d="M2.6 6.3l2.2 2.2 4.6-4.9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  bad: '<svg viewBox="0 0 12 12"><path d="M3.2 3.2l5.6 5.6M8.8 3.2l-5.6 5.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  warn: '<svg viewBox="0 0 12 12"><path d="M6 1.7l4.5 8H1.5z" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/><path d="M6 4.9v2.1" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><circle cx="6" cy="8.35" r=".7" fill="currentColor"/></svg>',
  merged: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.25"><circle cx="3.2" cy="2.6" r="1.25"/><circle cx="3.2" cy="9.4" r="1.25"/><circle cx="8.8" cy="6.6" r="1.25"/><path d="M3.2 3.9v4.2M3.2 3.9c0 2 1.4 2.7 4.3 2.7"/></svg>',
  github: '<svg viewBox="0 0 16 16"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>',
  link: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"><path d="M4.5 2.5h5v5M9.5 2.5L3 9"/></svg>',
};

// "Resolve conflicts" → "Resolving": what a decision's pill says while the agent carries it out,
// unless the action names it (busy_label).
const busyLabel = (a) => {
  if (a.busy_label) return str(a.busy_label);
  const w = (str(a.label || a.id).trim().split(/\s+/)[0] || "Work").toLowerCase();
  const ing = { stop: "stopping", run: "running", set: "setting", ship: "shipping", drop: "dropping", plan: "planning" }[w]
    || (w.endsWith("ing") ? w : /[^aeiou]e$/.test(w) ? `${w.slice(0, -1)}ing` : `${w}ing`);
  return ing[0].toUpperCase() + ing.slice(1);
};

// The rows the card draws (the PR's merge into its base on top once the PR exists, then the
// commits), their lanes, and the graph segments each row draws in its own cell. A cell's SVG spans
// the row's full height, so when a row grows in, the lines through it stretch with it and the graph
// never breaks.
function layout(p) {
  const base = str(p.base) || "main";
  const status = str(p.status);
  const commits = arr(p.commits).filter((c) => c && typeof c === "object");
  const prBranch = str((commits.find((c) => c.branch && c.branch !== base) || {}).branch);
  const laneOf = (c) => (c.branch === base ? 0 : !c.branch || c.branch === prBranch ? 1 : 2);
  const cf = p.conflicts && typeof p.conflicts === "object" ? p.conflicts : null;
  const total = cf ? num(cf.total) : 0;
  const resolved = cf ? Math.min(num(cf.resolved), total) : 0;
  const busy = BUSY.has(status);

  const rows = [];
  const hasTarget = p.pr !== undefined && p.pr !== null && p.pr !== "";
  if (hasTarget) rows.push({ key: "@target", target: true, lane: 0 });
  for (const c of commits) {
    const pending = c.state === "pending";
    rows.push({ key: c.sha && c.sha !== "-" ? `c:${c.sha}` : `p:${str(c.message)}`, c, lane: laneOf(c),
      uncommitted: pending && (!c.sha || c.sha === "-" || /uncommitted/i.test(str(c.message))) });
  }

  // Live progress on the row the work happens on: conflicts while resolving, a running check after.
  let progress = null;
  if (status === "resolving" && total) progress = { done: resolved, total };
  if (status === "checks_running" || status === "pushing_merge") {
    const run = arr(p.checks).find((k) => k && k.state === "running");
    if (run) {
      const m = /(\d+)\s*(?:\/|of)\s*(\d+)/.exec(str(run.detail));
      const t = num(run.total ?? (m && m[2]));
      if (t) progress = { done: Math.min(num(run.done ?? (m && m[1])), t), total: t };
    }
  }
  let active = -1;
  if (progress) {
    active = rows.findIndex((r) => r.c && r.c.state === "pending" && !r.uncommitted);
    if (active < 0) active = rows.findIndex((r) => r.c && r.lane === 1);
  }

  // Conflict numbers, top to bottom; while resolving, the first open one is the one being worked on.
  let n = 0, working = status === "resolving";
  const seenLane = new Set();
  rows.forEach((r, i) => {
    r.index = i;
    if (r.target) {
      r.text = `Merge into ${base}`;
      r.tone = "dim";
      if (status === "merged") { r.node = "merged"; r.meta = ["merged", "merged"]; r.chip = base; }
      else if (status === "ready") { r.node = "ok"; r.meta = ["ready", "ok"]; }
      else if (status === "failed") { r.node = "bad"; r.meta = ["blocked", "bad"]; }
      else if (status === "merging") { r.node = "spin"; r.meta = ["merging", "dim"]; }
      else if (total && resolved < total) { r.node = "warn"; r.meta = [plural(total - resolved, "conflict"), "warn"]; }
      else if (total) { r.node = busy ? "spin" : "ok"; r.meta = ["resolved", "ok"]; }
      else if (busy) { r.node = "spin"; r.meta = ["checking", "dim"]; }
      else { r.node = "ring"; r.meta = ["", "dim"]; }
      return;
    }
    const c = r.c;
    r.text = str(c.message);
    if (c.branch && !seenLane.has(r.lane)) r.chip = c.branch; // the label sits on each lane's tip
    seenLane.add(r.lane);
    if (c.state === "conflict" || c.state === "resolved") r.tag = { n: ++n, ok: c.state === "resolved" };
    const mine = /^you$/i.test(str(c.author));
    if (c.state === "pending") { r.node = r.uncommitted ? "pulse" : "spin"; r.tone = "dim"; }
    else if (c.state === "conflict") { r.node = working ? "spin" : "dot"; r.tone = "warn"; working = false; }
    else if (c.state === "resolved") { r.node = "dot"; r.tone = "dim"; }
    else { r.node = "dot"; r.tone = mine ? "strong" : "dim"; }
    if (i === active) r.meta = [`${progress.done}/${progress.total}`, "count"];
    else if (c.state === "pending") r.meta = [str(c.age), "dim"];
    else r.sha = [str(c.sha), [c.author, c.age].filter(Boolean).join(" · ")];
    if (i === active) r.progress = progress.done / progress.total;
  });

  // Segments: ["v", lane, y0, y1] a vertical run, ["c", lane, fromLane, y0, toLane, y1, dashed] a curve.
  const segs = rows.map(() => []);
  const at = (lane) => rows.map((r, i) => (!r.target && r.lane === lane ? i : -1)).filter((i) => i >= 0);
  const L0 = at(0), L1 = at(1), L2 = at(2);
  const baseRow = L0.length ? L0[L0.length - 1] : -1;
  if (L1.length) {
    const top = L1[0], bot = L1[L1.length - 1];
    const forked = baseRow > bot;
    if (hasTarget) {
      segs[0].push(["c", 1, 0, 50, 1, 100, status !== "merged"]);
      for (let r = 1; r < top; r++) segs[r].push(["v", 1, 0, 100]);
    }
    for (let r = top; r <= bot; r++) {
      const y0 = r === top && !hasTarget ? 50 : 0, y1 = r === bot && !forked ? 50 : 100;
      if (y0 < y1) segs[r].push(["v", 1, y0, y1]);
    }
    if (forked) {
      for (let r = bot + 1; r < baseRow; r++) segs[r].push(["v", 1, 0, 100]);
      segs[baseRow].push(["c", 1, 1, 0, 0, 50]);
    }
  }
  if (L0.length) {
    const top = L0[0], bot = baseRow;
    const mergeIn = new RegExp(`^merge\\b.*\\b${escapeRe(base)}\\b.*\\binto\\b`, "i");
    const into = L1.find((i) => i < top && mergeIn.test(rows[i].text));
    const from = into ?? top;
    for (let r = from; r <= bot; r++) {
      if (r === into) { segs[r].push(["c", 0, 0, 100, 1, 50]); continue; }
      const y0 = r === top && into === undefined ? 50 : 0, y1 = r === bot ? 50 : 100;
      if (y0 < y1) segs[r].push(["v", 0, y0, y1]);
    }
  }
  if (L2.length) {
    const t = L2[0], b = L2[L2.length - 1];
    segs[t].push(["c", 2, 2, 50, 1, 0]);
    if (t !== b) segs[t].push(["v", 2, 50, 100]);
    for (let r = t + 1; r < b; r++) segs[r].push(["v", 2, 0, 100]);
    if (t !== b) segs[b].push(["v", 2, 0, 50]);
    segs[b].push(["c", 2, 1, 100, 2, 50]);
  }
  rows.forEach((r, i) => {
    r.svg = segs[i].map((s) => {
      if (s[0] === "v") return `<path class="l${s[1]}" d="M${LANE_X[s[1]]} ${s[2]}V${s[3]}"/>`;
      const [, own, a, y0, b, y1, dashed] = s, ym = (y0 + y1) / 2;
      return `<path class="l${own}${dashed ? " dash" : ""}" d="M${LANE_X[a]} ${y0}C${LANE_X[a]} ${ym} ${LANE_X[b]} ${ym} ${LANE_X[b]} ${y1}"/>`;
    }).join("");
  });
  return { rows, base, status, total, resolved, busy };
}

GenUI.register("pr_card", (root, p, emit) => {
  const doc = root.ownerDocument;
  if (!doc.getElementById("gpr-style")) {
    const style = doc.createElement("style");
    style.id = "gpr-style";
    style.textContent = CSS;
    doc.head.append(style);
  }
  const el = (tag, cls, parent) => {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (parent) parent.append(n);
    return n;
  };

  const first = !root.__gpr;
  let ui = root.__gpr;
  if (first) {
    const card = el("article", "gpr");
    const hd = el("header", "gpr-hd", card);
    const title = el("span", "gpr-title", hd);
    ui = { card, hd, name: el("b", "gpr-name", title), num: el("span", "gpr-num", title), badge: el("span", "gpr-badge", hd) };
    ui.badgeText = el("span", "", ui.badge);
    ui.graph = el("div", "gpr-graph", card);
    ui.checks = el("div", "gpr-checks", card);
    ui.checks.hidden = true;
    ui.ex = el("p", "gpr-ex", card);
    ui.ex.hidden = true;
    ui.ft = el("footer", "gpr-ft", card);
    ui.status = el("span", "gpr-status", ui.ft);
    ui.icon = el("span", "gpr-icon", ui.status);
    ui.statusText = el("span", "gpr-status-text", ui.status);
    ui.acts = el("span", "gpr-acts", ui.ft);
    ui.pop = M.popover(card, "gpr-pop");
    root.replaceChildren(card);
    root.__gpr = ui;
  }
  ui.p = p;
  const L = layout(p);
  const { status, total, busy } = L;
  ui.card.dataset.status = status;
  const flash = getComputedStyle(ui.card).getPropertyValue("--gpr-flash").trim() || "rgba(210, 128, 26, .15)";

  // Header: the title, the PR number decoding in when the PR opens, the state badge.
  (first ? M.setText : M.decode)(ui.name, p.title);
  const pr = p.pr !== undefined && p.pr !== null && p.pr !== "" ? `#${p.pr}` : "";
  if (first || !pr) M.setText(ui.num, pr); else M.decode(ui.num, pr);
  const [tone, label] = status === "merged" ? ["merged", "Merged"] : status === "failed" ? ["bad", "Failed"] : pr ? ["ok", "Open"] : ["", ""];
  ui.badge.dataset.tone = tone;
  if (label && ui.badge.hidden !== false) { ui.badge.hidden = false; if (!first) M.fade(ui.badge, { y: 0, scale: 0.9 }); }
  if (!label) ui.badge.hidden = true;
  if (first) M.setText(ui.badgeText, label); else M.roll(ui.badgeText, label);

  // Commit graph.
  M.keyed(ui.graph, L.rows, {
    key: (r) => r.key,
    // A pending row (uncommitted changes, a merge being made) becomes the commit that lands on its lane.
    adopt: (node, r) => node.dataset.adopt === "1" && !r.target && node.dataset.lane === String(r.lane),
    create: () => {
      const row = el("div", "gpr-r");
      const lanes = el("span", "gpr-lanes", row);
      lanes.innerHTML = '<svg viewBox="0 0 40 100" preserveAspectRatio="none" aria-hidden="true"></svg>';
      el("span", "gpr-node", lanes);
      const msg = el("span", "gpr-msg", row);
      const tw = el("span", "gpr-tw", msg);
      el("span", "gpr-text", tw);
      el("i", "gpr-under", tw);
      el("code", "gpr-chip", msg).hidden = true;
      el("span", "gpr-tag", msg).hidden = true;
      const meta = el("span", "gpr-meta", row);
      el("span", "gpr-sha", meta);
      el("span", "gpr-who", meta);
      return row;
    },
    update: (row, r, { born, adopted }) => {
      const [lanes, msg, meta] = row.children;
      const [svg, node] = lanes.children;
      const [tw, chip, tag] = msg.children;
      const [text, under] = tw.children;
      row.className = r.target ? "gpr-r gpr-target" : "gpr-r gpr-row";
      row.dataset.lane = r.lane;
      row.dataset.tone = r.tone;
      row.dataset.adopt = r.c && r.c.state === "pending" ? "1" : "";
      row.style.setProperty("--d", `${r.index * 55}ms`);
      if (svg.__d !== r.svg) { svg.innerHTML = r.svg; svg.__d = r.svg; }
      node.style.left = `${LANE_X[r.lane]}px`;
      if (node.dataset.kind !== r.node) {
        const had = node.dataset.kind;
        node.dataset.kind = r.node;
        node.innerHTML = r.node === "warn" ? "!" : r.node === "ok" || r.node === "merged" ? ICONS.ok : "";
        if (had && !first) M.run(node, [{ transform: "translate(-50%,-50%) scale(.4)", opacity: 0.2 }, { transform: "translate(-50%,-50%) scale(1)", opacity: 1 }], { duration: 300 });
      }
      // Text: a new or adopted row, or a changed message, decodes into place.
      if (first) M.setText(text, r.text); else if (born || adopted || text.__target !== r.text) { if (born) M.setText(text, ""); M.decode(text, r.text); }
      chip.hidden = !r.chip;
      if (r.chip) M.setText(chip, r.chip);
      // Conflict badge: its number while open, a check once resolved.
      if (r.tag) {
        const kind = r.tag.ok ? "ok" : "num";
        const wasHidden = tag.hidden;
        tag.hidden = false;
        if (tag.dataset.kind !== kind || wasHidden) {
          const had = !wasHidden && tag.dataset.kind;
          tag.dataset.kind = kind;
          if (kind === "ok") tag.innerHTML = ICONS.ok; else tag.textContent = String(r.tag.n);
          if (!first) M.run(tag, [{ transform: "scale(.3)", opacity: 0 }, { transform: had ? "scale(1.18)" : "scale(1)", opacity: 1, offset: 0.7 }, { transform: "scale(1)", opacity: 1 }], { duration: 380 });
        } else if (kind === "num") M.setText(tag, String(r.tag.n));
      } else tag.hidden = true;
      // Progress: an underline that fills under the row's message.
      under.hidden = r.progress === undefined;
      if (r.progress !== undefined) under.style.width = `${Math.round(r.progress * 100)}%`;
      // Meta: sha and author, or a word, or a live count that rolls.
      const [sha, who] = meta.children;
      meta.dataset.tone = r.meta ? r.meta[1] : "";
      if (r.meta) {
        M.setText(sha, "");
        if (first || born) M.setText(who, r.meta[0]); else M.roll(who, r.meta[0]);
      } else {
        if (first || born || adopted) { M.setText(sha, r.sha[0]); } else M.roll(sha, r.sha[0]);
        M.setText(who, r.sha[1]);
      }
    },
    enter: (row) => {
      if (first) return;
      M.enter(row, { duration: 380 });
      M.run(row, [{ backgroundColor: flash }, { backgroundColor: flash, offset: 0.35 }, { backgroundColor: "transparent" }], { duration: 1600, easing: "ease-out" });
    },
    exit: (row) => { row.classList.remove("gpr-row", "gpr-target"); row.classList.add("gpr-gone"); M.exit(row); },
  });

  // Checks: pills that pop in one after another; hovering one shows what ran and how long it took.
  const checks = arr(p.checks).filter((k) => k && typeof k === "object");
  M.keyed(ui.checks, checks, {
    key: (k) => k.name,
    create: () => {
      const pill = el("span", "gpr-check");
      el("span", "gpr-check-icon", pill);
      el("span", "gpr-check-name", pill);
      el("span", "gpr-check-detail", pill);
      return pill;
    },
    update: (pill, k, { born }) => {
      const [icon, name, detail] = pill.children;
      const state = str(k.state) || "pending";
      if (pill.dataset.state !== state) {
        const had = pill.dataset.state;
        pill.dataset.state = state;
        icon.innerHTML = state === "passed" ? ICONS.ok : state === "failed" ? ICONS.bad : "";
        if (had && !first) M.run(icon, [{ transform: "scale(.3)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }], { duration: 280 });
      }
      M.setText(name, k.name);
      if (first || born) M.setText(detail, k.detail); else M.roll(detail, str(k.detail));
      detail.hidden = !k.detail;
      ui.pop.bind(pill, () => {
        const now = arr(ui.p.checks).find((x) => x && x.name === k.name) || k;
        const info = str(now.info) || (now.detail ? `${now.name} · ${now.detail}` : "");
        if (!info && !now.duration) return [];
        const row = el("div", "gpr-tip");
        el("span", "", row).textContent = info;
        if (now.duration) el("span", "gpr-tip-dim", row).textContent = str(now.duration);
        return row;
      });
    },
    enter: (pill, _k, j) => { if (!first) M.fade(pill, { delay: j * 70, y: 0, scale: 0.92, duration: 300 }); },
    exit: (pill) => M.exit(pill, { duration: 200 }),
  });
  const showChecks = checks.length > 0 && status !== "merged"; // merged: the checks fold away
  if (first) ui.checks.hidden = !showChecks; else M.toggle(ui.checks, showChecks);

  // Explanation, when the agent gives one in the card.
  const ex = str(p.explanation);
  if (ex && ui.ex.textContent !== ex) { ui.ex.textContent = ex; if (!first && !ui.ex.hidden) M.fade(ui.ex, { y: 2 }); }
  if (first) ui.ex.hidden = !ex; else M.toggle(ui.ex, !!ex);

  // Footer: the live status line (a shimmer while busy; "3 conflicts" opens what Lena changed),
  // and the pill: the decision, then its own busy state once clicked, then where the PR lives.
  const iconKind = busy ? "spin" : status === "conflicts" ? "warn" : status === "ready" ? "ok"
    : status === "merged" ? "merged" : status === "failed" ? "bad" : "idle";
  ui.status.dataset.state = iconKind;
  if (ui.icon.dataset.kind !== iconKind) {
    ui.icon.dataset.kind = iconKind;
    ui.icon.innerHTML = ICONS[iconKind] || "";
    if (!first) M.fade(ui.icon, { y: 0, scale: 0.6, duration: 240 });
  }
  const text = str(p.status_text) || STATUS_TEXT[status] || status.replace(/_/g, " ");
  const cf = p.conflicts && typeof p.conflicts === "object" ? p.conflicts : {};
  const detail = arr(cf.hunks).length || arr(cf.files).length;
  const hotMatch = (status === "conflicts" || status === "resolving") && total && detail ? /\d+\s+conflicts?/i.exec(text) : null;
  const statusKey = `${text}|${hotMatch ? 1 : 0}`;
  if (ui.statusText.__key !== statusKey) {
    ui.statusText.__key = statusKey;
    if (hotMatch) {
      const hot = el("span", "gpr-hot");
      hot.textContent = hotMatch[0];
      ui.statusText.replaceChildren(text.slice(0, hotMatch.index), hot, text.slice(hotMatch.index + hotMatch[0].length));
      ui.pop.bind(hot, () => conflictDetails(el, ui.p, L.base));
    } else ui.statusText.textContent = text;
    if (!first) M.run(ui.statusText, [{ opacity: 0, transform: "translateY(55%)" }, { opacity: 1, transform: "none" }], { duration: 300 });
  }
  ui.statusText.classList.toggle("gu-shimmer", busy);

  const actions = arr(p.actions).filter((a) => a && a.id);
  if (actions.length && ui.clicked && !actions.some((a) => a.id === ui.clicked.id)) ui.clicked = null;
  const pills = [];
  if (actions.length) actions.forEach((a) => pills.push({ kind: "action", key: `a:${a.id}`, a }));
  else if (busy && ui.clicked) pills.push({ kind: "busy", key: `a:${ui.clicked.id}` });
  else arr(p.links).filter((l) => l && l.url).forEach((l) => pills.push({ kind: "link", key: `l:${l.url}`, l }));
  if (!busy && !actions.length) ui.clicked = null;
  M.keyed(ui.acts, pills, {
    key: (x) => x.key,
    adopt: (node, x) => x.kind === "action" && node.tagName === "BUTTON",
    create: (x) => {
      if (x.kind === "link") {
        const a = el("a", "gpr-pill gpr-link");
        el("span", "gpr-pill-icon", a);
        el("span", "gpr-lbl", a);
        return a;
      }
      const b = el("button", "gpr-pill gpr-btn");
      b.type = "button";
      el("span", "gpr-pill-icon", b);
      el("span", "gpr-spin", b);
      el("span", "gpr-lbl", b);
      el("span", "gpr-busy", b);
      b.addEventListener("click", () => {
        if (b.disabled) return;
        const a = b.__action || {};
        ui.clicked = { id: a.id };
        // One click, one decision: the pill becomes its busy state until the agent answers.
        M.resize(b, () => { b.disabled = true; }, { axis: "width", duration: 260 });
        emit(a.id);
      });
      return b;
    },
    update: (n, x, { adopted }) => {
      const [icon] = n.children;
      if (x.kind === "link") {
        const isGh = /github\.com/i.test(x.l.url);
        n.dataset.kind = "link";
        icon.innerHTML = isGh ? ICONS.github : ICONS.link;
        M.setText(n.querySelector(".gpr-lbl"), x.l.label || (isGh ? "GitHub" : x.l.url));
        if (/^https?:\/\//i.test(x.l.url)) { n.href = x.l.url; n.target = "_blank"; n.rel = "noopener noreferrer"; }
        else n.removeAttribute("href");
        return;
      }
      const lbl = n.querySelector(".gpr-lbl"), busyEl = n.querySelector(".gpr-busy");
      if (x.kind === "action") {
        const a = x.a, prevId = n.dataset.action;
        n.__action = a;
        n.dataset.action = str(a.id);
        n.dataset.kind = ["primary", "secondary", "danger"].includes(a.kind) ? a.kind : "primary";
        icon.innerHTML = /merge/i.test(str(a.id)) ? ICONS.merged : "";
        M.setText(busyEl, busyLabel(a));
        if (adopted && prevId !== a.id) {
          // A busy pill becoming the next decision: same pill, new label, enabled again.
          M.resize(n, () => { n.disabled = false; M.setText(lbl, a.label || a.id); }, { axis: "width", duration: 300 });
          M.run(lbl, [{ opacity: 0, transform: "translateY(55%)" }, { opacity: 1, transform: "none" }], { duration: 300 });
        } else M.setText(lbl, a.label || a.id);
      }
    },
    enter: (n) => { if (!first) M.fade(n, { y: 0, scale: 0.9, duration: 280 }); },
    exit: (n) => M.exit(n, { duration: 200 }),
  });
  ui.pop.refresh();

  // First paint: the card builds itself. The header lands, then the commits arrive from the oldest
  // up while the card grows to fit them, then the status line.
  if (first) {
    const rows = [...ui.graph.children];
    const full = ui.card.getBoundingClientRect().height;
    const head = ui.hd.getBoundingClientRect().bottom - ui.card.getBoundingClientRect().top + 6;
    const span = 140 + rows.length * 42;
    M.run(ui.card, [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 300 });
    if (full > head) {
      ui.card.style.overflow = "hidden";
      const grow = M.run(ui.card, [{ height: `${head}px` }, { height: `${full}px` }], { duration: span + 220 });
      if (grow) grow.finished.then(() => { ui.card.style.overflow = ""; }, () => {});
      else ui.card.style.overflow = "";
    }
    rows.forEach((r, i) => M.fade(r, { delay: 110 + (rows.length - 1 - i) * 42, duration: 320, y: 5 }));
    M.fade(ui.checks, { delay: span, duration: 300 });
    M.fade(ui.ft, { delay: span + 40, duration: 300 });
  }
});

// What "3 conflicts" opens: who changed the same lines, and each conflicting line, theirs over ours.
function conflictDetails(el, p, base) {
  const cf = p.conflicts && typeof p.conflicts === "object" ? p.conflicts : {};
  const hunks = arr(cf.hunks).filter((h) => h && typeof h === "object");
  const out = [];
  const by = str((hunks.find((h) => h.by) || {}).by);
  const hd = el("div", "gpr-pop-hd");
  if (by) { el("b", "", hd).textContent = by; hd.append(` changed the same lines on ${base}`); }
  else hd.textContent = `Changed on ${base} and here`;
  out.push(hd);
  if (hunks.length) {
    for (const h of hunks.slice(0, 4)) {
      const box = el("div", "gpr-hunk");
      const file = el("div", "gpr-hunk-file", box);
      el("b", "", file).textContent = str(h.file);
      if (h.line) el("span", "", file).textContent = `line ${h.line}`;
      const lines = el("div", "gpr-hunk-lines", box);
      for (const [who, code] of [[str(h.by).split(/\s+/)[0] || base, h.theirs], ["You", h.ours]]) {
        if (code === undefined || code === null || code === "") continue;
        const ln = el("div", "gpr-hunk-line", lines);
        el("span", "gpr-hunk-who", ln).textContent = who;
        el("code", "", ln).textContent = str(code);
      }
      out.push(box);
    }
  } else {
    const list = el("div", "gpr-hunk-file");
    list.textContent = arr(cf.files).map(str).join(", ");
    out.push(list);
  }
  return out;
}

const CSS = `
@property --gpr-l0 { syntax: '<color>'; inherits: true; initial-value: transparent; }
@property --gpr-l1 { syntax: '<color>'; inherits: true; initial-value: transparent; }
@property --gpr-l2 { syntax: '<color>'; inherits: true; initial-value: transparent; }
.gpr {
  --gpr-fg: var(--foreground, #1f2328);
  --gpr-dim: var(--muted-foreground, #7d858f);
  --gpr-line: var(--border, color-mix(in srgb, var(--gpr-fg) 12%, transparent));
  --gpr-accent: var(--accent, #2f6fe4);
  --gpr-ok: #2f9a5f; --gpr-warn: #d2801a; --gpr-bad: #d04a3c; --gpr-merged: #8250df; --gpr-side: #1aa39a;
  --gpr-flash: color-mix(in srgb, var(--gpr-warn) 15%, transparent);
  --gpr-mono: var(--host-mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
  --gpr-l0: color-mix(in srgb, var(--gpr-fg) 32%, transparent); --gpr-l1: var(--gpr-accent); --gpr-l2: var(--gpr-side);
  --gu-shimmer-base: var(--gpr-dim); --gu-shimmer-hi: var(--gpr-fg);
  position: relative; box-sizing: border-box; padding: 11px 14px 10px;
  border: 1px solid var(--gpr-line); border-radius: 12px;
  background: var(--card, transparent);
  box-shadow: 0 1px 2px color-mix(in srgb, #000 4%, transparent);
  color: var(--gpr-fg); font: 13px/1.45 var(--host-font, system-ui, -apple-system, "Segoe UI", sans-serif);
}
.gpr[data-status=merged] { --gpr-l0: var(--gpr-merged); --gpr-l1: var(--gpr-merged); --gpr-l2: var(--gpr-merged); }
.gpr *, .gpr *::before { box-sizing: border-box; }
.gpr [hidden] { display: none !important; }

.gpr-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 7px; }
.gpr-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gpr-name { font-weight: 600; }
.gpr-num { margin-left: 5px; color: var(--gpr-dim); }
.gpr-badge { flex: none; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; color: var(--gpr-ok); transition: color .4s; }
.gpr-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.gpr-badge[data-tone=bad] { color: var(--gpr-bad); }
.gpr-badge[data-tone=merged] { color: var(--gpr-merged); }

.gpr-graph { display: grid; }
.gpr-r { position: relative; display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; align-items: center; column-gap: 4px;
  min-height: 24px; padding-right: 4px; border-radius: 6px; color: var(--gpr-fg);
  transition: --gpr-l0 .5s ease var(--d, 0ms), --gpr-l1 .5s ease var(--d, 0ms), --gpr-l2 .5s ease var(--d, 0ms), color .45s, background-color .3s; }
.gpr-r:hover { background: color-mix(in srgb, var(--gpr-fg) 4%, transparent); }
.gpr-r[data-tone=dim] { color: var(--gpr-dim); }
.gpr-r[data-tone=warn] { color: var(--gpr-warn); }
.gpr-lanes { position: relative; align-self: stretch; }
.gpr-lanes svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
.gpr-lanes path { fill: none; stroke-width: 1.5; vector-effect: non-scaling-stroke; stroke-linecap: round; }
.gpr-lanes path.l0 { stroke: var(--gpr-l0); } .gpr-lanes path.l1 { stroke: var(--gpr-l1); } .gpr-lanes path.l2 { stroke: var(--gpr-l2); }
.gpr-lanes path.dash { stroke-dasharray: 2.5 3; }
.gpr-node { position: absolute; top: 50%; width: 7px; height: 7px; border-radius: 50%; transform: translate(-50%, -50%);
  display: grid; place-items: center; background: var(--gpr-l1); color: #fff; font: 700 8.5px/1 var(--host-font, system-ui, sans-serif);
  transition: background-color .4s, box-shadow .4s; }
.gpr-r[data-lane="0"] .gpr-node { background: var(--gpr-l0); }
.gpr-r[data-lane="2"] .gpr-node { background: var(--gpr-l2); }
.gpr-r[data-tone=warn] .gpr-node { background: var(--gpr-warn); }
.gpr-node svg { width: 8px; height: 8px; }
.gpr-node[data-kind=ring] { background: var(--card, #fff) !important; box-shadow: inset 0 0 0 1.5px var(--gpr-dim); width: 9px; height: 9px; }
.gpr-node[data-kind=spin] { width: 10px; height: 10px; background: transparent !important; border: 1.5px solid color-mix(in srgb, var(--gpr-dim) 35%, transparent);
  border-top-color: var(--gpr-fg); animation: gpr-spin .75s linear infinite; }
.gpr-r[data-tone=warn] .gpr-node[data-kind=spin] { border-top-color: var(--gpr-warn); }
.gpr-node[data-kind=pulse] { width: 9px; height: 9px; background: var(--card, #fff) !important; box-shadow: inset 0 0 0 1.5px var(--gpr-l1); }
.gpr-node[data-kind=pulse]::after { content: ""; position: absolute; inset: -4px; border-radius: 50%; border: 1.5px solid var(--gpr-l1); animation: gpr-pulse 1.4s ease-out infinite; }
.gpr-node[data-kind=warn] { width: 13px; height: 13px; background: var(--gpr-warn) !important; }
.gpr-node[data-kind=ok] { width: 13px; height: 13px; background: var(--gpr-ok) !important; }
.gpr-node[data-kind=bad] { width: 11px; height: 11px; background: var(--gpr-bad) !important; }
.gpr-node[data-kind=merged] { width: 13px; height: 13px; background: var(--gpr-merged) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--gpr-merged) 22%, transparent); }

.gpr-msg { min-width: 0; display: flex; align-items: center; gap: 6px; overflow: hidden; white-space: nowrap; }
.gpr-tw { position: relative; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.gpr-under { position: absolute; left: 0; bottom: 1px; height: 1.5px; border-radius: 1px; background: var(--gpr-ok); width: 0;
  transition: width .6s cubic-bezier(.2,.75,.15,1); }
.gpr-chip { flex: none; padding: 0 5px; border-radius: 4px; font: 11px/17px var(--gpr-mono);
  color: var(--gpr-l1); background: color-mix(in srgb, var(--gpr-l1) 11%, transparent); transition: color .5s var(--d, 0ms), background-color .5s var(--d, 0ms); }
.gpr-r[data-lane="0"] .gpr-chip { color: var(--gpr-dim); background: color-mix(in srgb, var(--gpr-fg) 7%, transparent); }
.gpr[data-status=merged] .gpr-r[data-lane="0"] .gpr-chip { color: var(--gpr-merged); background: color-mix(in srgb, var(--gpr-merged) 11%, transparent); }
.gpr-r[data-lane="2"] .gpr-chip { color: var(--gpr-l2); background: color-mix(in srgb, var(--gpr-l2) 11%, transparent); }
.gpr-tag { flex: none; display: inline-grid; place-items: center; min-width: 15px; height: 15px; padding: 0 4px; border-radius: 4px;
  font: 600 10.5px/1 var(--gpr-mono); color: var(--gpr-warn); background: color-mix(in srgb, var(--gpr-warn) 14%, transparent); }
.gpr-tag[data-kind=ok] { padding: 0; width: 15px; border-radius: 50%; color: var(--gpr-ok); background: color-mix(in srgb, var(--gpr-ok) 15%, transparent); }
.gpr-tag svg { width: 9px; height: 9px; }
.gpr-meta { justify-self: end; display: inline-flex; gap: 7px; color: var(--gpr-dim); font-size: 11.5px; white-space: nowrap; }
.gpr-sha { font: 11px var(--gpr-mono); opacity: .8; }
.gpr-sha:empty { display: none; }
.gpr-meta[data-tone=warn] { color: var(--gpr-warn); }
.gpr-meta[data-tone=ok] { color: var(--gpr-ok); }
.gpr-meta[data-tone=bad] { color: var(--gpr-bad); }
.gpr-meta[data-tone=merged] { color: var(--gpr-merged); }
.gpr-meta[data-tone=count] { color: var(--gpr-fg); font: 11px var(--gpr-mono); }

.gpr-checks { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 9px; padding-left: 2px; }
.gpr-check { display: inline-flex; align-items: center; gap: 5px; max-width: 100%; padding: 2px 9px 2px 7px; border-radius: 999px;
  border: 1px solid var(--gpr-line); font-size: 12px; white-space: nowrap; cursor: default; transition: border-color .3s, background-color .2s; }
.gpr-check:hover { background: color-mix(in srgb, var(--gpr-fg) 4%, transparent); }
.gpr-check-icon { display: grid; place-items: center; width: 10px; height: 10px; color: var(--gpr-dim); }
.gpr-check-icon svg { width: 10px; height: 10px; }
.gpr-check[data-state=passed] .gpr-check-icon { color: var(--gpr-ok); }
.gpr-check[data-state=failed] { border-color: color-mix(in srgb, var(--gpr-bad) 45%, transparent); }
.gpr-check[data-state=failed] .gpr-check-icon, .gpr-check[data-state=failed] .gpr-check-detail { color: var(--gpr-bad); }
.gpr-check[data-state=running] .gpr-check-icon { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid color-mix(in srgb, var(--gpr-dim) 35%, transparent);
  border-top-color: var(--gpr-fg); animation: gpr-spin .75s linear infinite; }
.gpr-check[data-state=pending] .gpr-check-icon::before { content: ""; width: 4px; height: 4px; border-radius: 50%; background: currentColor; }
.gpr-check-detail { color: var(--gpr-dim); }

.gpr-ex { margin: 9px 0 0; color: var(--gpr-dim); font-size: 12.5px; white-space: normal; }
.gpr-ft { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 26px; margin-top: 8px; }
.gpr-status { min-width: 0; display: inline-flex; align-items: center; gap: 7px; }
.gpr-icon { flex: none; display: grid; place-items: center; width: 12px; height: 12px; color: var(--gpr-dim); }
.gpr-icon svg { width: 12px; height: 12px; }
.gpr-status[data-state=spin] .gpr-icon { width: 11px; height: 11px; border-radius: 50%; border: 1.5px solid color-mix(in srgb, var(--gpr-dim) 35%, transparent);
  border-top-color: var(--gpr-fg); animation: gpr-spin .75s linear infinite; }
.gpr-status[data-state=warn] .gpr-icon { color: var(--gpr-warn); }
.gpr-status[data-state=ok] .gpr-icon { color: var(--gpr-ok); }
.gpr-status[data-state=merged] .gpr-icon { color: var(--gpr-merged); }
.gpr-status[data-state=bad] .gpr-icon { color: var(--gpr-bad); }
.gpr-status-text { display: inline-block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gpr-hot { color: var(--gpr-warn); text-decoration: underline dotted; text-decoration-thickness: 1px; text-underline-offset: 3px; cursor: default; }

.gpr-acts { flex: none; display: inline-flex; gap: 6px; }
.gpr-pill { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 26px; padding: 0 12px; border-radius: 999px;
  font: 500 12.5px/1 var(--host-font, system-ui, sans-serif); white-space: nowrap; overflow: hidden; text-decoration: none; border: 0; cursor: pointer;
  color: var(--gpr-accent); background: color-mix(in srgb, var(--gpr-accent) 12%, transparent);
  transition: background-color .25s, color .25s, transform .12s; }
.gpr-pill:hover:not(:disabled) { background: color-mix(in srgb, var(--gpr-accent) 19%, transparent); }
.gpr-pill:active:not(:disabled) { transform: scale(.97); }
.gpr-pill:focus-visible { outline: 2px solid var(--gpr-accent); outline-offset: 2px; }
.gpr-pill[data-kind=secondary] { color: var(--gpr-fg); background: color-mix(in srgb, var(--gpr-fg) 7%, transparent); }
.gpr-pill[data-kind=danger] { color: var(--gpr-bad); background: color-mix(in srgb, var(--gpr-bad) 11%, transparent); }
.gpr-pill[data-kind=link] { color: var(--gpr-fg); background: color-mix(in srgb, var(--gpr-fg) 6%, transparent); }
.gpr-pill-icon { display: grid; place-items: center; }
.gpr-pill-icon:empty { display: none; }
.gpr-pill-icon svg { width: 12px; height: 12px; }
.gpr-spin, .gpr-busy { display: none; }
.gpr-btn:disabled { cursor: default; color: var(--gpr-dim); background: color-mix(in srgb, var(--gpr-fg) 6%, transparent); }
.gpr-btn:disabled .gpr-lbl, .gpr-btn:disabled .gpr-pill-icon { display: none; }
.gpr-btn:disabled .gpr-busy { display: inline; }
.gpr-btn:disabled .gpr-spin { display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 1.5px solid color-mix(in srgb, var(--gpr-dim) 35%, transparent); border-top-color: var(--gpr-fg); animation: gpr-spin .75s linear infinite; }

.gpr-pop { padding: 8px 10px; border-radius: 10px; border: 1px solid var(--gpr-line); background: var(--card, #fff);
  box-shadow: 0 10px 28px color-mix(in srgb, #000 14%, transparent), 0 1px 3px color-mix(in srgb, #000 6%, transparent);
  color: var(--gpr-fg); font-size: 12px; line-height: 1.45; white-space: nowrap; }
.gpr-pop-hd { color: var(--gpr-dim); padding-bottom: 6px; margin-bottom: 6px; border-bottom: 1px solid var(--gpr-line); }
.gpr-pop-hd b { color: var(--gpr-fg); font-weight: 600; }
.gpr-hunk + .gpr-hunk { margin-top: 8px; }
.gpr-hunk-file { display: flex; gap: 6px; align-items: baseline; margin-bottom: 3px; }
.gpr-hunk-file b { font: 600 11.5px var(--gpr-mono); }
.gpr-hunk-file span { color: var(--gpr-dim); font-size: 11px; }
.gpr-hunk-lines { border-left: 2px solid color-mix(in srgb, var(--gpr-warn) 55%, transparent); padding-left: 8px; }
.gpr-hunk-line { display: flex; gap: 8px; font: 11px/1.6 var(--gpr-mono); }
.gpr-hunk-who { width: 32px; flex: none; color: var(--gpr-dim); font-family: var(--host-font, system-ui, sans-serif); }
.gpr-tip { display: flex; gap: 12px; align-items: baseline; font: 11px var(--gpr-mono); }
.gpr-tip-dim { color: var(--gpr-dim); }

@keyframes gpr-spin { to { transform: rotate(360deg); } }
.gpr-node[data-kind=spin] { animation-name: gpr-node-spin; }
@keyframes gpr-node-spin { from { transform: translate(-50%, -50%) rotate(0); } to { transform: translate(-50%, -50%) rotate(360deg); } }
@keyframes gpr-pulse { from { opacity: .7; transform: scale(.6); } to { opacity: 0; transform: scale(1.5); } }
@media (max-width: 460px) { .gpr-who { display: none; } }
@media (prefers-reduced-motion: reduce) {
  .gpr, .gpr * { animation-duration: 1ms !important; animation-iteration-count: 1 !important; transition: none !important; }
}
`;
})();
