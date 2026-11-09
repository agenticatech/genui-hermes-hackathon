// Default theme for task_card, drawn with the default card kit (kit.js) so it reads like pr_card.
// The plan is a spine: each step's node fills the line as it is reached, the running step spins and
// carries the live progress as an underline, the step that needs the user pulses, a failure turns
// red, and a rollback forks off the failed step as its own branch. Figures count to their new values
// (memory falls from 15.6 to 6.2 GB, the gauge empties), findings slide in one after another, a
// stopped process is struck through. On success the line turns green from top to bottom.
// A theme only draws props: emit(action_id) hands a decision back to the agent.
(() => {
const M = GenUI.motion, K = window.GenUICard;
const { arr, str } = K;
const BADGE = { waiting: ["warn", "Needs you"], done: ["ok", "Done"], failed: ["bad", "Failed"], cancelled: ["", "Cancelled"] };
const ICON = { running: "spin", waiting: "wait", done: "ok", failed: "bad", cancelled: "idle" };
const RECOVERY = /\b(roll(ing)?[\s_-]?back|revert|restore|recover)/i;
const GONE = /^(stopped|killed|terminated|removed|deleted)\b/i;
const KEPT = /\b(kept|spared|protected|as you asked)\b/i;
const zero = (s) => str(s).replace(/\d+(?:[.,]\d+)?/g, (m) => m.replace(/\d/g, "0"));

GenUI.register("task_card", (root, p, emit) => {
  let ui = root.__gtk;
  if (!ui) {
    ui = root.__gtk = K.shell(root, "gtk");
    const doc = root.ownerDocument;
    if (!doc.getElementById("gtk-style")) {
      const style = doc.createElement("style");
      style.id = "gtk-style";
      style.textContent = CSS;
      doc.head.append(style);
    }
    ui.steps = ui.el("div", "gtk-steps", ui.body);
    ui.metrics = ui.el("div", "gtk-metrics", ui.body);
    ui.metrics.hidden = true;
    ui.items = ui.el("div", "gtk-items", ui.body);
    ui.items.hidden = true;
  }
  const first = ui.first, el = ui.el;
  const status = str(p.status);
  ui.card.dataset.status = status;
  ui.card.dataset.end = status === "done" ? "ok" : "";
  ui.p = p;
  K.header(ui, { title: p.title, sub: p.subtitle, badge: BADGE[status] });

  // The spine.
  const steps = arr(p.steps).filter((s) => s && typeof s === "object");
  const prog = p.progress && typeof p.progress === "object" && Number(p.progress.total) > 0 ? p.progress : null;
  let lastFailed = -1, waitingMarked = false;
  const rows = steps.map((s, i) => {
    const state = str(s.state) || "pending";
    const r = { s, state, index: i, lane: 0, reached: ["running", "done", "failed"].includes(state) };
    if (lastFailed >= 0 && RECOVERY.test(`${str(s.id)} ${str(s.label)}`)) { r.lane = 1; r.from = lastFailed; }
    if (state === "failed") lastFailed = i;
    return r;
  });
  const lastReached = rows.reduce((k, r, i) => (r.reached ? i : k), -1);
  rows.forEach((r, i) => {
    const st = r.state;
    if (st === "running") r.kind = "spin";
    else if (st === "failed") r.kind = "bad";
    else if (st === "blocked") r.kind = "warn";
    else if (st === "skipped") r.kind = "skip";
    else if (st === "done") r.kind = status === "done" && i === lastReached ? "ok" : "dot";
    else if (status === "waiting" && !waitingMarked && !rows.some((x) => x.state === "running")) { r.kind = "wait"; waitingMarked = true; }
    else r.kind = "ring";
    r.tone = st === "failed" ? "bad" : st === "pending" || st === "skipped" ? "dim" : "";
    if (st === "running" && prog) {
      const done = Math.min(Number(prog.done) || 0, Number(prog.total));
      r.meta = [`${prog.label ? `${prog.label} ` : ""}${done}/${prog.total}`, "count"];
      r.progress = done / Number(prog.total);
    } else r.meta = [str(r.s.detail), st === "failed" ? "bad" : ""];
  });
  const svgs = K.spine(rows);
  const log = arr(p.log).slice(-5).map(str);

  M.keyed(ui.steps, rows, {
    key: (r) => r.s.id,
    create: () => K.spineRow(el),
    update: (row, r, { born }) => {
      K.paintSpineRow(row, { svg: svgs[r.index], lane: r.lane, kind: r.kind, first, index: r.index });
      row.className = "gc-r gtk-step";
      row.dataset.state = r.state;
      row.dataset.tone = r.tone;
      const text = row.querySelector(".gc-text"), under = row.querySelector(".gc-under"), meta = row.querySelector(".gc-meta");
      const label = str(r.s.label);
      if (first) M.setText(text, label);
      else if (born || text.__target !== label) { if (born) M.setText(text, ""); M.decode(text, label); }
      under.hidden = r.progress === undefined;
      if (r.progress !== undefined) under.style.width = `${Math.round(r.progress * 100)}%`;
      meta.dataset.tone = r.meta[1];
      const was = meta.__target ?? "";
      if (first) M.setText(meta, r.meta[0]);
      else if (!was || born) M.decode(meta, r.meta[0]);
      else M.tween(meta, r.meta[0]);
      // Hovering the step that is running (or failed) shows its last lines of output.
      if ((r.state === "running" || r.state === "failed") && log.length) {
        ui.pop.bind(row, () => {
          const lines = arr(ui.p.log).slice(-5).map(str);
          if (!lines.length) return [];
          const hd = el("div", "gc-pop-hd");
          el("b", "", hd).textContent = label;
          hd.append(" · last output");
          const pre = el("pre", "gc-pop-log");
          lines.forEach((l, i) => { const b = el(i === lines.length - 1 ? "b" : "span", "", pre); b.textContent = l + (i < lines.length - 1 ? "\n" : ""); });
          return [hd, pre];
        });
      } else ui.pop.bind(row, () => []);
    },
    enter: (row) => {
      if (first) return;
      M.enter(row, { duration: 380 });
      const flash = getComputedStyle(ui.card).getPropertyValue("--gc-flash").trim() || "rgba(47, 111, 228, .13)";
      M.run(row, [{ backgroundColor: flash }, { backgroundColor: "transparent" }], { duration: 1400, easing: "ease-out" });
    },
    exit: (row) => M.exit(row),
  });

  // Figures: values count to their new numbers; "x / y" values draw a gauge that fills or empties.
  const metrics = arr(p.metrics).filter((m) => m && m.label);
  M.keyed(ui.metrics, metrics, {
    key: (m) => m.label,
    create: () => {
      const m = el("span", "gtk-metric");
      const top = el("span", "gtk-mtop", m);
      el("b", "gtk-mv", top);
      el("span", "gtk-ml", top);
      el("i", "gtk-gauge", el("span", "gtk-bar", m));
      return m;
    },
    update: (m, x, { born }) => {
      const [top, bar] = m.children;
      const [v, l] = top.children;
      m.dataset.tone = str(x.tone) || "neutral";
      M.setText(l, x.label);
      if (first) M.setText(v, x.value);
      else if (born) { M.setText(v, zero(x.value)); M.tween(v, str(x.value), { duration: 900 }); }
      else M.tween(v, str(x.value), { duration: 900 });
      const r = K.ratio(x.value);
      bar.hidden = r === null;
      if (r !== null) {
        const gauge = bar.firstChild;
        if (born && !first) { gauge.style.width = "0%"; void gauge.offsetWidth; }
        gauge.style.width = `${Math.round(r * 100)}%`;
      }
    },
    enter: (m, _x, j) => { if (!first) M.fade(m, { delay: j * 80, y: 4, duration: 320 }); },
    exit: (m) => M.exit(m, { duration: 200 }),
  });
  if (first) ui.metrics.hidden = !metrics.length; else M.toggle(ui.metrics, metrics.length > 0);

  // Findings: rows slide in one after another; the culprit is tinted; a stopped one is struck through.
  const items = arr(p.items).filter((x) => x && typeof x === "object");
  M.keyed(ui.items, items, {
    key: (x) => x.id,
    create: () => {
      const row = el("div", "gtk-item");
      el("span", "gtk-dot", row);
      const main = el("span", "gtk-imain", row);
      el("span", "gtk-ilabel gc-strike", main);
      el("span", "gtk-kept", main).hidden = true;
      el("span", "gtk-idetail", main);
      el("span", "gtk-ivalue", row);
      return row;
    },
    update: (row, x, { born }) => {
      const [, main, value] = row.children;
      const [label, kept, detail] = main.children;
      const gone = GONE.test(str(x.detail));
      row.dataset.tone = str(x.tone) || "neutral";
      row.classList.toggle("is-gone", gone);
      M.setText(label, x.label);
      label.classList.toggle("is-on", gone);
      const isKept = KEPT.test(str(x.detail));
      kept.hidden = !isKept;
      if (isKept && !kept.innerHTML) kept.innerHTML = `${K.ICONS.lock}<span>kept</span>`;
      const d = str(x.detail).replace(/\s*·?\s*kept, as you asked/i, "");
      if (first || born) M.setText(detail, d); else if (detail.__target !== d) M.decode(detail, d);
      if (first || born) M.setText(value, x.value); else M.tween(value, str(x.value));
    },
    enter: (row, _x, j) => { if (!first) M.enter(row, { delay: j * 70, duration: 360 }); },
    exit: (row) => M.exit(row),
  });
  if (first) ui.items.hidden = !items.length; else M.toggle(ui.items, items.length > 0);

  K.explain(ui, p.explanation);
  K.status(ui, { kind: ICON[status] || "idle", text: str(p.status_text) || (BADGE[status] || ["", status])[1], busy: status === "running" });
  K.pills(ui, { actions: p.actions, links: p.links, busy: status === "running", emit });
  ui.pop.refresh();
  if (first) K.build(ui, [...ui.steps.children, ...ui.metrics.children, ...ui.items.children]);
  ui.first = false;
});

const CSS = `
.gtk-steps { display: grid; }
.gtk-step[data-state=pending] .gc-meta, .gtk-step[data-state=skipped] .gc-meta { opacity: .7; }
.gtk-metrics { display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 10px 0 2px 6px; }
.gtk-metric { display: inline-flex; flex-direction: column; gap: 4px; min-width: 104px; color: var(--gc-fg); }
.gtk-metric[data-tone=good] { color: var(--gc-ok); }
.gtk-metric[data-tone=warn] { color: var(--gc-warn); }
.gtk-metric[data-tone=bad] { color: var(--gc-bad); }
.gtk-metric { transition: color .6s; }
.gtk-mtop { display: inline-flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.gtk-mv { font: 600 12.5px var(--gc-mono); }
.gtk-ml { color: var(--gc-dim); font-size: 11.5px; }
.gtk-bar { display: block; height: 3px; border-radius: 2px; overflow: hidden; background: color-mix(in srgb, var(--gc-fg) 9%, transparent); }
.gtk-gauge { display: block; height: 100%; width: 0; border-radius: 2px; background: currentColor; transition: width .9s cubic-bezier(.2,.75,.15,1), background-color .6s; }
.gtk-items { display: grid; margin-top: 9px; padding-top: 5px; border-top: 1px solid var(--gc-line); }
.gtk-item { display: grid; grid-template-columns: 12px minmax(0, 1fr) auto; align-items: center; column-gap: 8px; min-height: 28px;
  padding: 0 6px; border-radius: 6px; transition: background-color .4s, opacity .5s; }
.gtk-item[data-tone=bad] { background: color-mix(in srgb, var(--gc-bad) 8%, transparent); }
.gtk-item[data-tone=warn] { background: color-mix(in srgb, var(--gc-warn) 8%, transparent); }
.gtk-item.is-gone { opacity: .55; }
.gtk-dot { width: 6px; height: 6px; border-radius: 50%; justify-self: center; background: color-mix(in srgb, var(--gc-fg) 28%, transparent); transition: background-color .4s; }
.gtk-item[data-tone=bad] .gtk-dot { background: var(--gc-bad); }
.gtk-item[data-tone=warn] .gtk-dot { background: var(--gc-warn); }
.gtk-item[data-tone=good] .gtk-dot { background: var(--gc-ok); }
.gtk-imain { min-width: 0; display: flex; align-items: baseline; gap: 8px; overflow: hidden; white-space: nowrap; }
.gtk-ilabel { overflow: hidden; text-overflow: ellipsis; }
.gtk-idetail { color: var(--gc-dim); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; }
.gtk-kept { flex: none; display: inline-flex; align-items: center; gap: 3px; padding: 0 6px 0 5px; border-radius: 999px; font-size: 11px; line-height: 17px;
  color: var(--gc-ok); background: color-mix(in srgb, var(--gc-ok) 11%, transparent); }
.gtk-kept svg { width: 10px; height: 10px; }
.gtk-ivalue { font: 11.5px var(--gc-mono); color: var(--gc-dim); white-space: nowrap; }
.gtk-item[data-tone=bad] .gtk-ivalue { color: var(--gc-bad); font-weight: 600; }
@media (max-width: 460px) { .gtk-idetail { display: none; } }
`;
})();
