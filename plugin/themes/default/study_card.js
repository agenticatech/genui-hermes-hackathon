// Default theme for study_card, drawn with the default card kit (kit.js). The session plan is a
// spine like task_card's. The quiz runs in the card, one question at a time: the user picks an
// option, the right one turns green (theirs red if wrong), the explanation decodes in, the dots and
// the step's count fill, and Next folds the question away for the following one. Once every question
// is answered the score counts up and the agent's action appears; its click carries the answers
// (values {quiz, answers: {question id: option id}, score, total}). Mastery bars fill per topic, the
// lesson's ideas decode in one after another, flashcards flip, and planned reviews pop to "set".
// A theme only draws props and the user's own clicks: nothing leaves the card but emit().
(() => {
const M = GenUI.motion, K = window.GenUICard;
const { arr, str } = K;
const BADGE = { quiz: ["warn", "Your turn"], waiting: ["warn", "Needs you"], done: ["ok", "Done"], failed: ["bad", "Failed"] };
const ICON = { running: "spin", quiz: "wait", waiting: "wait", done: "ok", failed: "bad" };
const LETTERS = "ABCDE";
const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0));
const pct = (m) => `${Math.round(clamp01(m) * 100)}%`;
const level = (m) => (m < 0.5 ? "low" : m < 0.8 ? "mid" : "high");

GenUI.register("study_card", (root, p, emit) => {
  let ui = root.__gsc;
  if (!ui) {
    ui = root.__gsc = K.shell(root, "gsc");
    const doc = root.ownerDocument;
    if (!doc.getElementById("gsc-style")) {
      const style = doc.createElement("style");
      style.id = "gsc-style";
      style.textContent = CSS;
      doc.head.append(style);
    }
    const el = ui.el, sec = (title) => {
      const s = el("div", "gsc-sec", ui.body);
      s.hidden = true;
      const t = el("div", "gsc-sec-title", s);
      t.textContent = title;
      return [s, t];
    };
    ui.steps = el("div", "gsc-steps", ui.body);
    ui.quiz = el("div", "gsc-quiz", ui.body);
    ui.quiz.hidden = true;
    const qhd = el("div", "gsc-qhd", ui.quiz);
    ui.qcount = el("span", "gsc-qcount", qhd);
    ui.dots = el("span", "gsc-dots", qhd);
    ui.stage = el("div", "gsc-stage", ui.quiz);
    [ui.topics] = sec("Where you stand");
    ui.topicList = el("div", "gsc-topics", ui.topics);
    [ui.lesson, ui.lessonTitle] = sec("");
    ui.points = el("ol", "gsc-points", ui.lesson);
    ui.cards = el("div", "gsc-cards", ui.lesson);
    [ui.sched] = sec("Reviews");
    ui.schedList = el("div", "gsc-sched", ui.sched);
  }
  const first = ui.first, el = ui.el;
  ui.p = p;
  ui.emit = emit;
  const status = str(p.status);
  ui.card.dataset.status = status;
  ui.card.dataset.end = status === "done" ? "ok" : "";
  K.header(ui, { title: p.title, sub: p.subtitle, badge: BADGE[status] });

  // The plan.
  const rows = arr(p.steps).filter((s) => s && typeof s === "object").map((s, i) => {
    const state = str(s.state) || "pending";
    return { s, state, index: i, lane: 0, reached: ["running", "done", "failed"].includes(state) };
  });
  const lastReached = rows.reduce((k, r, i) => (r.reached ? i : k), -1);
  const svgs = K.spine(rows);
  M.keyed(ui.steps, rows, {
    key: (r) => r.s.id,
    create: () => K.spineRow(el),
    update: (row, r, { born }) => {
      const kind = r.state === "running" ? (status === "quiz" || status === "waiting" ? "wait" : "spin") : r.state === "failed" ? "bad" : r.state === "skipped" ? "skip"
        : r.state === "done" ? (status === "done" && r.index === lastReached ? "ok" : "dot") : "ring";
      K.paintSpineRow(row, { svg: svgs[r.index], lane: 0, kind, first, index: r.index });
      row.className = "gc-r gsc-step";
      row.dataset.state = r.state;
      row.dataset.tone = r.state === "pending" || r.state === "skipped" ? "dim" : r.state === "failed" ? "bad" : "";
      const text = row.querySelector(".gc-text"), meta = row.querySelector(".gc-meta"), under = row.querySelector(".gc-under");
      const label = str(r.s.label);
      if (first) M.setText(text, label);
      else if (born || text.__target !== label) { if (born) M.setText(text, ""); M.decode(text, label); }
      const d = str(r.s.detail);
      meta.dataset.tone = "";
      if (first) M.setText(meta, d); else if (!meta.__target || born) M.decode(meta, d); else M.tween(meta, d);
      under.hidden = true;
    },
    enter: (row) => { if (!first) M.enter(row, { duration: 380 }); },
    exit: (row) => M.exit(row),
  });

  // The quiz: local state per round, kept across the agent's repaints.
  const quiz = p.quiz && typeof p.quiz === "object" && arr(p.quiz.questions).length ? p.quiz : null;
  if (quiz && (!ui.q || ui.q.id !== str(quiz.id))) ui.q = { id: str(quiz.id), idx: 0, answers: {}, done: false };
  if (!quiz) ui.q = null;
  if (first) ui.quiz.hidden = !quiz; else M.toggle(ui.quiz, !!quiz);
  if (quiz) renderQuiz(ui, first);

  // Mastery per topic: bars fill, figures count.
  const topics = arr(p.topics).filter((t) => t && t.id);
  M.keyed(ui.topicList, topics, {
    key: (t) => t.id,
    create: () => {
      const row = el("div", "gsc-topic");
      const main = el("span", "gsc-tmain", row);
      el("span", "gsc-tlabel", main);
      el("span", "gsc-tnote", main);
      el("i", "", el("span", "gsc-tbar", row));
      el("span", "gsc-tpct", row);
      return row;
    },
    update: (row, t, { born }) => {
      const [main, bar, num] = row.children;
      const [label, note] = main.children;
      const m = clamp01(t.mastery);
      row.dataset.level = level(m);
      M.setText(label, t.label);
      const n = str(t.note);
      if (first || born) M.setText(note, n); else if (note.__target !== n) M.decode(note, n);
      const fill = bar.firstChild;
      if (born && !first) { fill.style.width = "0%"; M.setText(num, "0%"); void fill.offsetWidth; }
      fill.style.width = pct(m);
      if (first) M.setText(num, pct(m)); else M.tween(num, pct(m), { duration: 1000 });
    },
    enter: (row, _t, j) => { if (!first) M.enter(row, { delay: j * 90, duration: 360 }); },
    exit: (row) => M.exit(row),
  });
  if (first) ui.topics.hidden = !topics.length; else M.toggle(ui.topics, topics.length > 0);

  // The lesson: its ideas decode in one after another; its flashcards flip on click.
  const lesson = p.lesson && typeof p.lesson === "object" ? p.lesson : null;
  if (lesson) {
    const t = str(lesson.title);
    if (first || ui.lesson.hidden) M.setText(ui.lessonTitle, t); else if (ui.lessonTitle.__target !== t) M.decode(ui.lessonTitle, t);
    let born = 0;
    M.keyed(ui.points, arr(lesson.points).map(str), {
      key: (s) => s,
      create: () => { const li = el("li", "gsc-point"); el("span", "gsc-pnum", li); el("span", "gsc-ptext", li); return li; },
      update: (li, s, { index, born: isNew }) => {
        li.firstChild.textContent = String(index + 1);
        const tx = li.lastChild;
        if (first || !isNew) M.setText(tx, s);
        else { M.setText(tx, ""); const delay = 250 + born++ * 380; setTimeout(() => M.decode(tx, s, { duration: 700 }), delay); }
      },
      enter: (li, _s, j) => { if (!first) M.enter(li, { delay: j * 380, duration: 340 }); },
      exit: (li) => M.exit(li),
    });
    M.keyed(ui.cards, arr(lesson.cards).filter((c) => c && c.front), {
      key: (c) => c.front,
      create: () => {
        const b = el("button", "gsc-flip");
        b.type = "button";
        const inner = el("span", "gsc-flip-in", b);
        const front = el("span", "gsc-face gsc-front", inner);
        el("span", "gsc-ftext", front);
        el("small", "", front).textContent = "Flip";
        const back = el("span", "gsc-face gsc-back", inner);
        el("span", "gsc-ftext", back);
        b.addEventListener("click", () => b.classList.toggle("is-flipped"));
        return b;
      },
      update: (b, c) => {
        const [front, back] = b.firstChild.children;
        M.setText(front.firstChild, c.front);
        M.setText(back.firstChild, c.back);
      },
      enter: (b, _c, j) => { if (!first) M.fade(b, { delay: 300 + arr(lesson.points).length * 380 + j * 120, y: 6, scale: 0.96, duration: 360 }); },
      exit: (b) => M.exit(b, { duration: 220 }),
    });
  }
  if (first) ui.lesson.hidden = !lesson; else M.toggle(ui.lesson, !!lesson);

  // Reviews: each planned slot pops to "set" once its reminder exists.
  const slots = arr(p.schedule).filter((s) => s && s.id);
  let popped = 0;
  M.keyed(ui.schedList, slots, {
    key: (s) => s.id,
    create: () => {
      const row = el("div", "gsc-slot");
      el("span", "gsc-snode", row);
      el("span", "gsc-when", row);
      el("span", "gsc-slabel", row);
      el("span", "gsc-sstate", row);
      return row;
    },
    update: (row, s, { born }) => {
      const [node, when, label, st] = row.children;
      const state = str(s.state) || "planned";
      M.setText(when, s.when);
      M.setText(label, s.label);
      if (row.dataset.state !== state) {
        const had = row.dataset.state;
        row.dataset.state = state;
        node.innerHTML = state === "planned" ? "" : K.ICONS.ok;
        const word = state === "set" ? "reminder set" : state === "done" ? "reviewed" : "planned";
        if (had && !first) {
          const delay = popped++ * 160;
          M.run(node, [{ transform: "scale(.3)", opacity: 0 }, { transform: "scale(1.2)", opacity: 1, offset: 0.7 }, { transform: "scale(1)", opacity: 1 }], { duration: 420, delay });
          setTimeout(() => M.roll(st, word), delay);
        } else M.setText(st, word);
      }
    },
    enter: (row, _s, j) => { if (!first) M.enter(row, { delay: j * 90, duration: 340 }); },
    exit: (row) => M.exit(row),
  });
  if (first) ui.sched.hidden = !slots.length; else M.toggle(ui.sched, slots.length > 0);

  K.explain(ui, p.explanation);
  K.status(ui, { kind: ICON[status] || "idle", text: str(p.status_text) || (status === "quiz" ? "Answer in the card" : (BADGE[status] || ["", status])[1]), busy: status === "running" });
  footer(ui, first);
  syncStep(ui);
  ui.pop.refresh();
  if (first) K.build(ui, [...ui.steps.children]);
  ui.first = false;
});

// The pill: hidden while a quiz still has unanswered questions; its click carries the answers. A
// finished quiz always offers a way to send them, even when the agent named no action for it.
const SUBMIT = { id: "submit_quiz", label: "Send my answers", kind: "primary", busy_label: "Sending" };
function footer(ui, first) {
  const p = ui.p, status = str(p.status);
  const pending = ui.q && !ui.q.done;
  const offered = arr(p.actions).filter((a) => a && a.id);
  ui.first = first;
  K.pills(ui, {
    actions: pending ? [] : ui.q && ui.q.done && !offered.length ? [SUBMIT] : p.actions,
    links: p.links,
    busy: status === "running",
    emit: ui.emit,
    values: () => (ui.q ? { quiz: ui.q.id, answers: { ...ui.q.answers }, score: score(ui), total: questions(ui).length } : {}),
  });
}

const questions = (ui) => arr(ui.p.quiz && ui.p.quiz.questions).filter((q) => q && q.id);
const score = (ui) => questions(ui).filter((q) => ui.q.answers[q.id] === str(q.answer)).length;

// The running step shows the quiz's own count and fills its underline as questions are answered.
function syncStep(ui) {
  if (!ui.q) return;
  const row = [...ui.steps.children].find((r) => r.dataset.state === "running");
  if (!row) return;
  const n = questions(ui).length, done = Object.keys(ui.q.answers).length;
  const meta = row.querySelector(".gc-meta"), under = row.querySelector(".gc-under");
  meta.dataset.tone = "count";
  M.roll(meta, `${done}/${n}`);
  under.hidden = false;
  under.style.width = `${Math.round((done / Math.max(1, n)) * 100)}%`;
}

function renderQuiz(ui, first) {
  const el = ui.el, qs = questions(ui), q = ui.q, n = qs.length;
  if (q.idx >= n) q.idx = n - 1;
  const answeredAll = qs.every((x) => q.answers[x.id] !== undefined);
  const right = score(ui);
  const head = q.done ? `${right} of ${n} right` : `Question ${q.idx + 1} of ${n}`;
  if (first || !ui.qcount.__target) M.setText(ui.qcount, head); else M.roll(ui.qcount, head);

  M.keyed(ui.dots, qs, {
    key: (x) => x.id,
    create: () => el("span", "gsc-qdot"),
    update: (d, x, { index }) => {
      const a = q.answers[x.id];
      d.dataset.state = a === undefined ? (index === q.idx && !q.done ? "now" : "todo") : a === str(x.answer) ? "right" : "wrong";
    },
  });

  const items = q.done ? [{ key: `${q.id}:score` }] : [{ key: `${q.id}:${qs[q.idx].id}`, x: qs[q.idx] }];
  M.keyed(ui.stage, items, {
    key: (it) => it.key,
    create: (it) => (it.x ? questionNode(ui, it.x) : summaryNode(ui)),
    update: (node, it) => { if (it.x) paintQuestion(ui, node, it.x, false); },
    enter: (node) => { if (!first) M.enter(node, { duration: 380 }); },
    exit: (node) => M.exit(node, { duration: 280 }),
  });
  if (answeredAll && !q.done && q.idx === n - 1 && ui.stage.querySelector(".gsc-next")) {
    ui.stage.querySelector(".gsc-next .gc-lbl").textContent = "See my score";
  }
}

function questionNode(ui, x) {
  const el = ui.el;
  const node = el("div", "gsc-q");
  el("p", "gsc-prompt", node);
  const opts = el("div", "gsc-opts", node);
  arr(x.options).forEach((o, i) => {
    const b = el("button", "gsc-opt", opts);
    b.type = "button";
    b.dataset.opt = str(o.id);
    el("span", "gsc-letter", b).textContent = LETTERS[i] || String(i + 1);
    el("span", "gsc-olabel", b).textContent = str(o.label);
    el("span", "gsc-omark", b);
    b.addEventListener("click", () => {
      if (ui.q.answers[x.id] !== undefined) return;
      ui.q.answers[x.id] = str(o.id);
      paintQuestion(ui, node, x, true);
      renderQuiz(ui, false);
      syncStep(ui);
    });
  });
  const ex = el("div", "gsc-explain", node);
  ex.hidden = true;
  const nav = el("div", "gsc-qnav", node);
  const next = el("button", "gc-pill gsc-next", nav);
  next.type = "button";
  next.dataset.kind = "secondary";
  el("span", "gc-lbl", next).textContent = "Next question";
  next.hidden = true;
  next.addEventListener("click", () => {
    const n = questions(ui).length;
    if (ui.q.idx >= n - 1) ui.q.done = true; else ui.q.idx += 1;
    renderQuiz(ui, false);
    footer(ui, false);
  });
  paintQuestion(ui, node, x, false);
  return node;
}

// Marks an answered question: the right option green, the user's red if it was not the right one,
// the others faded; then the explanation decodes in and Next appears.
function paintQuestion(ui, node, x, fresh) {
  const prompt = node.querySelector(".gsc-prompt");
  M.setText(prompt, x.prompt);
  const a = ui.q.answers[x.id], ok = str(x.answer);
  for (const b of node.querySelectorAll(".gsc-opt")) {
    const id = b.dataset.opt;
    const res = a === undefined ? "" : id === ok ? (id === a ? "right" : "answer") : id === a ? "wrong" : "other";
    b.disabled = a !== undefined;
    if (b.dataset.res === res) continue;
    b.dataset.res = res;
    const mark = b.querySelector(".gsc-omark");
    mark.innerHTML = res === "right" || res === "answer" ? K.ICONS.ok : res === "wrong" ? K.ICONS.bad : "";
    if (fresh && mark.innerHTML) M.run(mark, [{ transform: "scale(.3)", opacity: 0 }, { transform: "scale(1.25)", opacity: 1, offset: 0.65 }, { transform: "scale(1)", opacity: 1 }], { duration: 380, delay: res === "answer" ? 160 : 0 });
    if (fresh && res === "wrong") M.run(b, [{ transform: "translateX(0)" }, { transform: "translateX(-4px)" }, { transform: "translateX(4px)" }, { transform: "translateX(-2px)" }, { transform: "translateX(0)" }], { duration: 320 });
  }
  const ex = node.querySelector(".gsc-explain"), next = node.querySelector(".gsc-next");
  if (a !== undefined) {
    const text = ((a === ok ? "Right. " : "Not quite. ") + str(x.explain)).trim();
    if (fresh) { M.toggle(ex, true); M.setText(ex, ""); M.decode(ex, text, { duration: 650 }); }
    else if (ex.__target !== text) { ex.hidden = false; M.setText(ex, text); } // never cut a decode in flight
    ex.dataset.res = a === ok ? "right" : "wrong";
    if (next.hidden) { next.hidden = false; if (fresh) M.fade(next, { delay: 350, y: 0, scale: 0.92, duration: 260 }); }
    const last = ui.q.idx >= questions(ui).length - 1;
    next.querySelector(".gc-lbl").textContent = last ? "See my score" : "Next question";
  }
}

// The round's score counts up; the topics missed are named under it.
function summaryNode(ui) {
  const el = ui.el, qs = questions(ui), n = qs.length, right = score(ui);
  const node = el("div", "gsc-summary");
  const big = el("span", "gsc-score", node);
  M.setText(big, `0/${n}`);
  requestAnimationFrame(() => M.tween(big, `${right}/${n}`, { duration: 900 }));
  const line = el("span", "gsc-missed", node);
  const missed = [...new Set(qs.filter((x) => ui.q.answers[x.id] !== str(x.answer)).map((x) => {
    const t = arr(ui.p.topics).find((tp) => tp && tp.id === x.topic);
    const raw = t ? str(t.label) : str(x.topic).replace(/[_-]+/g, " ");
    return raw ? raw[0].toUpperCase() + raw.slice(1) : "";
  }).filter(Boolean))];
  line.textContent = right === n ? "All right. Send your answers to move on." : missed.length ? `Missed: ${missed.join(", ")}` : `${n - right} to review`;
  return node;
}

const CSS = `
.gsc-steps { display: grid; }
.gsc-sec { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--gc-line); }
.gsc-sec-title { margin: 0 0 6px 2px; font-size: 11.5px; color: var(--gc-dim); }
.gsc-sec-title:empty { display: none; }

.gsc-quiz { margin-top: 10px; padding: 10px 12px 12px; border-radius: 10px; border: 1px solid var(--gc-line);
  background: color-mix(in srgb, var(--gc-fg) 2.5%, transparent); }
.gsc-qhd { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 9px; font-size: 11.5px; color: var(--gc-dim); }
.gsc-dots { display: inline-flex; gap: 5px; }
.gsc-qdot { width: 18px; height: 4px; border-radius: 2px; background: color-mix(in srgb, var(--gc-fg) 12%, transparent); transition: background-color .35s; }
.gsc-qdot[data-state=now] { background: color-mix(in srgb, var(--gc-accent) 55%, transparent); }
.gsc-qdot[data-state=right] { background: var(--gc-ok); }
.gsc-qdot[data-state=wrong] { background: var(--gc-bad); }
.gsc-prompt { margin: 0 0 9px; font-size: 13.5px; font-weight: 500; line-height: 1.45; }
.gsc-opts { display: grid; gap: 6px; }
.gsc-opt { display: grid; grid-template-columns: 20px minmax(0, 1fr) 16px; align-items: center; gap: 9px; padding: 7px 10px; border-radius: 8px;
  border: 1px solid var(--gc-line); background: var(--card, transparent); color: var(--gc-fg); font: inherit; text-align: left; cursor: pointer;
  transition: border-color .2s, background-color .3s, opacity .35s, transform .12s; }
.gsc-opt:hover:not(:disabled) { border-color: color-mix(in srgb, var(--gc-accent) 50%, transparent); background: color-mix(in srgb, var(--gc-accent) 5%, var(--card, transparent)); }
.gsc-opt:active:not(:disabled) { transform: scale(.99); }
.gsc-opt:focus-visible { outline: 2px solid var(--gc-accent); outline-offset: 2px; }
.gsc-opt:disabled { cursor: default; }
.gsc-letter { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 6px; font: 600 11px var(--gc-mono); color: var(--gc-dim);
  background: color-mix(in srgb, var(--gc-fg) 6%, transparent); transition: background-color .3s, color .3s; }
.gsc-olabel { line-height: 1.4; }
.gsc-omark { display: grid; place-items: center; width: 16px; height: 16px; }
.gsc-omark svg { width: 13px; height: 13px; }
.gsc-opt[data-res=right], .gsc-opt[data-res=answer] { border-color: color-mix(in srgb, var(--gc-ok) 55%, transparent); background: color-mix(in srgb, var(--gc-ok) 9%, var(--card, transparent)); }
.gsc-opt[data-res=right] .gsc-letter, .gsc-opt[data-res=answer] .gsc-letter { background: var(--gc-ok); color: #fff; }
.gsc-opt[data-res=right] .gsc-omark, .gsc-opt[data-res=answer] .gsc-omark { color: var(--gc-ok); }
.gsc-opt[data-res=wrong] { border-color: color-mix(in srgb, var(--gc-bad) 55%, transparent); background: color-mix(in srgb, var(--gc-bad) 8%, var(--card, transparent)); }
.gsc-opt[data-res=wrong] .gsc-letter { background: var(--gc-bad); color: #fff; }
.gsc-opt[data-res=wrong] .gsc-omark { color: var(--gc-bad); }
.gsc-opt[data-res=other] { opacity: .45; }
.gsc-explain { margin: 9px 2px 0; padding-left: 9px; border-left: 2px solid var(--gc-ok); color: var(--gc-dim); font-size: 12.5px; line-height: 1.5; }
.gsc-explain[data-res=wrong] { border-left-color: var(--gc-bad); }
.gsc-qnav { display: flex; justify-content: flex-end; margin-top: 9px; }
.gsc-qnav:has(.gsc-next[hidden]) { display: none; }
.gsc-summary { display: flex; align-items: baseline; gap: 12px; padding: 2px 2px 0; }
.gsc-score { font: 600 24px/1.1 var(--gc-mono); }
.gsc-missed { color: var(--gc-dim); font-size: 12.5px; }

.gsc-topics { display: grid; }
.gsc-topic { display: grid; grid-template-columns: minmax(0, 1fr) minmax(70px, 140px) 38px; align-items: center; column-gap: 10px; min-height: 26px; padding: 0 4px; }
.gsc-tmain { min-width: 0; display: flex; align-items: baseline; gap: 8px; overflow: hidden; white-space: nowrap; }
.gsc-tlabel { overflow: hidden; text-overflow: ellipsis; }
.gsc-tnote { color: var(--gc-dim); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; }
.gsc-tbar { display: block; height: 5px; border-radius: 3px; overflow: hidden; background: color-mix(in srgb, var(--gc-fg) 9%, transparent); }
.gsc-tbar i { display: block; height: 100%; width: 0; border-radius: 3px; background: var(--gc-ok); transition: width 1s cubic-bezier(.2,.75,.15,1), background-color .6s; }
.gsc-topic[data-level=low] .gsc-tbar i { background: var(--gc-bad); }
.gsc-topic[data-level=mid] .gsc-tbar i { background: var(--gc-warn); }
.gsc-tpct { text-align: right; font: 11.5px var(--gc-mono); color: var(--gc-dim); }

.gsc-points { margin: 0; padding: 0; list-style: none; display: grid; gap: 5px; }
.gsc-point { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 6px; align-items: baseline; font-size: 12.8px; line-height: 1.5; }
.gsc-pnum { display: grid; place-items: center; width: 16px; height: 16px; border-radius: 50%; font: 600 10px var(--gc-mono); color: var(--gc-accent);
  background: color-mix(in srgb, var(--gc-accent) 12%, transparent); transform: translateY(2px); }
.gsc-cards { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.gsc-cards:empty { display: none; }
.gsc-flip { flex: 1 1 150px; padding: 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; perspective: 700px; }
.gsc-flip-in { display: grid; transform-style: preserve-3d; transition: transform .6s cubic-bezier(.2,.75,.15,1); }
.gsc-flip.is-flipped .gsc-flip-in { transform: rotateY(180deg); }
.gsc-face { grid-area: 1 / 1; display: flex; flex-direction: column; justify-content: center; gap: 4px; min-height: 74px; padding: 9px 11px;
  border-radius: 9px; border: 1px solid var(--gc-line); background: var(--card, #fff); backface-visibility: hidden; -webkit-backface-visibility: hidden;
  font-size: 12.5px; line-height: 1.45; transition: border-color .2s; }
.gsc-flip:hover .gsc-face { border-color: color-mix(in srgb, var(--gc-accent) 45%, transparent); }
.gsc-front small { color: var(--gc-dim); font-size: 10.5px; }
.gsc-back { transform: rotateY(180deg); background: color-mix(in srgb, var(--gc-accent) 8%, var(--card, #fff)); }

.gsc-sched { display: grid; }
.gsc-slot { display: grid; grid-template-columns: 16px minmax(90px, auto) minmax(0, 1fr) auto; align-items: center; column-gap: 9px; min-height: 26px; padding: 0 4px; }
.gsc-snode { display: grid; place-items: center; width: 13px; height: 13px; border-radius: 50%; color: #fff;
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--gc-fg) 30%, transparent); transition: background-color .3s, box-shadow .3s; }
.gsc-snode svg { width: 8px; height: 8px; }
.gsc-slot[data-state=set] .gsc-snode, .gsc-slot[data-state=done] .gsc-snode { background: var(--gc-ok); box-shadow: none; }
.gsc-when { font: 11.5px var(--gc-mono); color: var(--gc-dim); white-space: nowrap; }
.gsc-slabel { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gsc-sstate { font-size: 11.5px; color: var(--gc-dim); white-space: nowrap; }
.gsc-slot[data-state=set] .gsc-sstate { color: var(--gc-ok); }
@media (max-width: 460px) { .gsc-tnote { display: none; } .gsc-topic { grid-template-columns: minmax(0, 1fr) 70px 38px; } }
`;
})();
