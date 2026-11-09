// Default theme for review_list, drawn with the default card kit (kit.js). The checkboxes carry
// data-field="selected" and value=<item id>, so the host sends the user's selection with their click
// as values.selected; emit(action_id) only names the decision. The user's ticks survive the agent's
// updates: an item's box follows props.selected when the item appears or when that prop changes,
// never on an unrelated repaint.
// Motion: scanned items slide in one after another while their sizes count up; the selected total
// counts as you tick; while the action runs, the ticked rows spin; once done, each deleted row is
// struck through and folds away into one "deleted" line while the freed space counts up.
(() => {
const M = GenUI.motion, K = window.GenUICard;
const { arr, str } = K;
const BADGE = { review: ["warn", "Your call"], done: ["ok", "Done"], failed: ["bad", "Failed"] };
const ICON = { scanning: "spin", review: "wait", applying: "spin", done: "ok", failed: "bad" };
const size = (mb) => {
  const v = Number(mb) || 0;
  return v >= 1024 ? `${(v / 1024).toFixed(1)} GB` : v < 1 ? "<1 MB" : `${Math.round(v)} MB`;
};
const zero = (s) => str(s).replace(/\d+(?:[.,]\d+)?/g, (m) => m.replace(/\d/g, "0"));

GenUI.register("review_list", (root, p, emit) => {
  let ui = root.__grl;
  if (!ui) {
    ui = root.__grl = K.shell(root, "grl");
    const doc = root.ownerDocument;
    if (!doc.getElementById("grl-style")) {
      const style = doc.createElement("style");
      style.id = "grl-style";
      style.textContent = CSS;
      doc.head.append(style);
    }
    const el = ui.el;
    ui.list = el("div", "grl-list", ui.body);
    ui.gone = el("div", "grl-gone", ui.body);
    ui.gone.hidden = true;
    ui.goneIcon = el("span", "grl-gone-icon", ui.gone);
    ui.goneIcon.innerHTML = K.ICONS.ok;
    ui.goneText = el("span", "gc-hot", ui.gone);
    ui.foot = el("div", "grl-foot", ui.body);
    ui.picked = el("span", "grl-picked", ui.foot);
    ui.pickedN = el("span", "grl-n", ui.picked);
    ui.picked.append(" selected");
    ui.pickedMb = el("span", "grl-mb", ui.picked);
    ui.freed = el("span", "grl-freed", ui.foot);
    ui.freed.hidden = true;
    // Display only: how much the current ticks add up to.
    ui.list.addEventListener("change", () => tally(ui));
    ui.pop.bind(ui.goneText, () => {
      const done = arr(ui.p.items).filter((x) => x && x.state === "done");
      return done.slice(0, 8).map((x) => {
        const row = el("div", "gc-pop-row");
        el("span", "", row).textContent = str(x.label || x.id);
        el("span", "", row).textContent = x.size_mb === undefined ? "" : size(x.size_mb);
        return row;
      });
    });
  }
  const first = ui.first, el = ui.el;
  ui.p = p;
  const status = str(p.status);
  const actions = arr(p.actions);
  // Ticking makes sense while the user reviews, not once the action runs.
  const editable = actions.length > 0 && !["applying", "done", "failed"].includes(status);
  ui.card.dataset.status = status;
  ui.card.dataset.end = status === "done" ? "ok" : "";
  K.header(ui, { title: p.title, sub: p.subtitle, badge: BADGE[status] });

  const items = arr(p.items).filter((x) => x && typeof x === "object");
  let folding = 0;
  M.keyed(ui.list, items, {
    key: (it) => it.id,
    create: () => {
      const row = el("label", "grl-row");
      row.dataset.row = "";
      const pick = el("span", "grl-pick", row);
      const box = el("input", "grl-box", pick);
      box.type = "checkbox";
      box.dataset.field = "selected";
      el("span", "grl-spin", pick);
      el("span", "grl-mark", pick);
      const main = el("span", "grl-main", row);
      el("span", "grl-label gc-strike", main);
      el("span", "grl-detail", main);
      el("span", "gc-tag grl-tag", row);
      el("span", "grl-size", row);
      return row;
    },
    update: (row, it, { born }) => {
      const [pick, main, tag, sz] = row.children;
      const [box, , mark] = pick.children;
      const [label, detail] = main.children;
      box.value = str(it.id);
      const sel = !!it.selected;
      if (row.__sel !== sel) { box.checked = sel; row.__sel = sel; }
      if (it.locked) box.checked = false;
      box.disabled = !!it.locked || !editable;
      const state = str(it.state);
      row.dataset.tone = str(it.tone) || "neutral";
      row.dataset.state = state;
      row.classList.toggle("is-locked", !!it.locked);
      row.dataset.size = it.size_mb === undefined ? "" : String(it.size_mb);
      const name = str(it.label || it.id);
      if (first || born) M.setText(label, name); else if (label.__target !== name) M.decode(label, name);
      const d = str(it.detail);
      if (first || born || !detail.__target) M.setText(detail, d); else if (detail.__target !== d) M.decode(detail, d);
      detail.hidden = !d;
      tag.hidden = !it.tag;
      tag.dataset.tone = it.locked ? "warn" : str(it.tone) === "good" ? "good" : str(it.tone) === "warn" ? "warn" : str(it.tone) === "bad" ? "bad" : "";
      tag.innerHTML = it.locked ? K.ICONS.lock : "";
      tag.append(str(it.tag));
      const s = it.size_mb === undefined ? "" : size(it.size_mb);
      if (first) M.setText(sz, s);
      else if (born) { M.setText(sz, zero(s)); M.tween(sz, s, { duration: 900 }); }
      else M.tween(sz, s);
      mark.innerHTML = state === "done" ? K.ICONS.ok : state === "failed" ? K.ICONS.bad : "";
      // Deleted: struck through, then folded into the "deleted" line, one row after another.
      if (state === "done" && row.__state !== "done") {
        if (first) { row.hidden = true; }
        else {
          const delay = folding++ * 110;
          row.style.setProperty("--sd", `${delay}ms`);
          void label.offsetWidth;
          label.classList.add("is-on");
          setTimeout(() => M.exit(row, { keep: true, duration: 320 }), 650 + delay);
        }
      }
      if (state !== "done") { label.classList.remove("is-on"); if (row.__state === "done") M.toggle(row, true); }
      row.__state = state;
      // Locked rows say why on hover.
      ui.pop.bind(row, () => {
        const now = arr(ui.p.items).find((x) => x && str(x.id) === str(it.id)) || it;
        if (!now.locked && now.state !== "failed") return [];
        const hd = el("div", "gc-pop-hd");
        el("b", "", hd).textContent = str(now.label || now.id);
        const why = el("div", "");
        why.textContent = now.state === "failed" ? `Not deleted: ${str(now.detail)}`
          : /open|in use/i.test(str(now.tag)) ? "Open in another program: left alone" : `Left alone${now.tag ? `: ${now.tag}` : ""}`;
        return [hd, why];
      });
    },
    enter: (row, _it, j) => { if (!first) M.enter(row, { delay: j * 55, duration: 340 }); },
    exit: (row) => M.exit(row),
  });

  const sm = p.summary && typeof p.summary === "object" ? p.summary : {};
  ui.list.dataset.total = sm.total_mb === undefined ? "" : String(sm.total_mb);
  tally(ui);
  const showPicked = !["done", "failed"].includes(status) && items.length > 0;
  if (first) ui.picked.hidden = !showPicked; else M.toggle(ui.picked, showPicked);

  // What is gone, and how much space came back.
  const done = items.filter((x) => x.state === "done");
  const goneMb = sm.freed_mb !== undefined ? Number(sm.freed_mb) || 0 : done.reduce((t, x) => t + (Number(x.size_mb) || 0), 0);
  const goneText = `${done.length} deleted${goneMb ? ` · ${size(goneMb)} freed` : ""}`;
  if (done.length) {
    if (first || ui.gone.hidden) M.setText(ui.goneText, goneText); else M.tween(ui.goneText, goneText);
    if (first) ui.gone.hidden = false;
    // It opens while the deleted rows fold, and its figures count up as they go.
    else if (ui.gone.hidden) setTimeout(() => { M.toggle(ui.gone, true); M.setText(ui.goneText, zero(goneText)); M.tween(ui.goneText, goneText, { duration: 1100 }); }, 450 + folding * 110);
  } else if (!ui.gone.hidden) M.toggle(ui.gone, false);
  // The freed figure on its own, when no row carries it (the "deleted" line already does).
  const freed = done.length ? "" : sm.freed_mb !== undefined ? `${size(sm.freed_mb)} freed` : str(sm.note);
  if (freed) {
    ui.freed.dataset.tone = sm.freed_mb !== undefined ? "ok" : "neutral";
    if (first) { M.setText(ui.freed, freed); ui.freed.hidden = false; }
    else if (ui.freed.hidden) { ui.freed.hidden = false; M.setText(ui.freed, zero(freed)); M.tween(ui.freed, freed, { duration: 1100 + folding * 110 }); M.fade(ui.freed, { y: 0 }); }
    else M.tween(ui.freed, freed);
  } else ui.freed.hidden = true;

  K.explain(ui, p.explanation);
  K.status(ui, { kind: ICON[status] || "idle", text: str(p.status_text) || (BADGE[status] || ["", status])[1], busy: status === "scanning" || status === "applying" });
  K.pills(ui, { actions, busy: status === "scanning" || status === "applying", emit });
  ui.pop.refresh();
  if (first) K.build(ui, [...ui.list.children]);
  ui.first = false;
});

function tally(ui) {
  let n = 0, mb = 0, any = false;
  for (const row of ui.list.children) {
    const box = row.querySelector("input");
    if (!box) continue;
    if (row.dataset.size !== "") any = true;
    row.classList.toggle("is-picked", box.checked);
    if (box.checked && row.dataset.state !== "done") { n += 1; mb += Number(row.dataset.size) || 0; }
  }
  const total = Number(ui.list.dataset.total) || 0;
  if (ui.pickedN.__target === undefined) M.setText(ui.pickedN, String(n)); else M.roll(ui.pickedN, String(n));
  const rest = (any && mb ? ` · ${size(mb)}` : "") + (total ? ` of ${size(total)}` : "");
  if (ui.pickedMb.__target === undefined) M.setText(ui.pickedMb, rest); else M.tween(ui.pickedMb, rest, { duration: 400 });
}

const CSS = `
.grl-list { display: grid; }
.grl-row { display: grid; grid-template-columns: 22px minmax(0, 1fr) auto auto; align-items: center; column-gap: 8px; min-height: 31px;
  padding: 0 6px; border-radius: 7px; cursor: pointer; transition: background-color .25s, opacity .4s; }
.grl-row:hover { background: color-mix(in srgb, var(--gc-fg) 4%, transparent); }
.grl-row.is-picked { background: color-mix(in srgb, var(--gc-accent) 6%, transparent); }
.grl-row.is-locked { cursor: default; }
.grl-row.is-locked .grl-main { opacity: .6; }
.grl-row[data-state=failed] { background: color-mix(in srgb, var(--gc-bad) 8%, transparent); }
.grl-row[data-state=failed] .grl-detail { color: var(--gc-bad); }
.grl-pick { position: relative; display: grid; place-items: center; width: 18px; height: 18px; }
.grl-box { appearance: none; -webkit-appearance: none; margin: 0; width: 15px; height: 15px; border-radius: 4px; cursor: pointer;
  border: 1.5px solid color-mix(in srgb, var(--gc-fg) 30%, transparent); background: transparent; display: grid; place-items: center;
  transition: background-color .18s, border-color .18s, opacity .2s; }
.grl-box::after { content: ""; width: 7px; height: 4px; border: 1.8px solid #fff; border-top: 0; border-right: 0;
  transform: translateY(-1px) rotate(-45deg) scale(0); transition: transform .2s cubic-bezier(.2,.75,.15,1.4); }
.grl-box:checked { background: var(--gc-accent); border-color: var(--gc-accent); }
.grl-box:checked::after { transform: translateY(-1px) rotate(-45deg) scale(1); }
.grl-box:disabled { cursor: default; opacity: .5; }
.grl-box:focus-visible { outline: 2px solid var(--gc-accent); outline-offset: 2px; }
.grl-spin, .grl-mark { position: absolute; display: none; place-items: center; }
.grl[data-status=applying] .grl-row.is-picked .grl-box { opacity: 0; }
.grl[data-status=applying] .grl-row.is-picked .grl-spin { display: block; width: 12px; height: 12px; border-radius: 50%;
  border: 1.5px solid color-mix(in srgb, var(--gc-dim) 35%, transparent); border-top-color: var(--gc-fg); animation: gc-spin .75s linear infinite; }
.grl-row[data-state=done] .grl-box, .grl-row[data-state=failed] .grl-box { opacity: 0; }
.grl-row[data-state=done] .grl-mark, .grl-row[data-state=failed] .grl-mark { display: grid; width: 15px; height: 15px; border-radius: 50%; color: #fff; }
.grl-row[data-state=done] .grl-mark { background: var(--gc-ok); }
.grl-row[data-state=failed] .grl-mark { background: var(--gc-bad); }
.grl-mark svg { width: 9px; height: 9px; }
.grl-main { min-width: 0; display: flex; align-items: baseline; gap: 9px; overflow: hidden; white-space: nowrap; }
.grl-label { overflow: hidden; text-overflow: ellipsis; }
.grl-detail { color: var(--gc-dim); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; }
.grl-tag { display: inline-flex; align-items: center; gap: 3px; }
.grl-tag svg { width: 10px; height: 10px; }
.grl-size { min-width: 52px; text-align: right; font: 11.5px var(--gc-mono); color: var(--gc-dim); }
.grl-row.is-picked .grl-size { color: var(--gc-fg); }
.grl-gone { display: flex; align-items: center; gap: 8px; min-height: 30px; padding: 0 6px; color: var(--gc-ok); }
.grl-gone-icon { display: grid; place-items: center; width: 15px; height: 15px; margin-left: 2px; border-radius: 50%; background: var(--gc-ok); color: #fff; }
.grl-gone-icon svg { width: 9px; height: 9px; }
.grl-foot { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; margin: 6px 6px 0; font-size: 12px; color: var(--gc-dim); }
.grl-n { font-variant-numeric: tabular-nums; color: var(--gc-fg); }
.grl-mb { white-space: pre; }
.grl-freed { margin-left: auto; font: 600 12.5px var(--gc-mono); }
.grl-freed[data-tone=ok] { color: var(--gc-ok); }
@media (max-width: 460px) { .grl-detail { display: none; } }
`;
})();
