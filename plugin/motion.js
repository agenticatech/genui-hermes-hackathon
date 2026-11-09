// GenUI motion kit: the moves themes animate their updates with, exposed as GenUI.motion. Loaded
// ahead of the runtime in the Desktop's frame (library.frame_payload) and ahead of the themes in
// the benchmark's host page, so a theme animates the same everywhere.
// Every change a card shows should read as a change: rows open a gap and grow in, text decodes into
// its new value, figures roll, sections fold. It all runs on the Web Animations API, so an animation
// never leaves inline styles behind, and size changes animate layout properties (height, width), so
// the frame's ResizeObserver sees each step and the Desktop frame follows the card frame by frame.
(() => {
  if (window.GenUIMotion) return;
  const EASE = 'cubic-bezier(.2,.75,.15,1)';
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  const run = (el, frames, opts = {}) => {
    if (!el.animate) return null;
    const o = { easing: EASE, fill: 'backwards', ...opts };
    if (reduced()) { o.duration = 1; o.delay = 0; }
    return el.animate(frames, o);
  };

  // Box sizes an element collapses from and grows back to.
  const BOX = ['height', 'paddingTop', 'paddingBottom', 'marginTop', 'marginBottom'];
  const boxOf = (el) => {
    const cs = getComputedStyle(el);
    const box = { height: el.getBoundingClientRect().height + 'px' };
    for (const k of BOX.slice(1)) box[k] = cs[k];
    return box;
  };
  const ZERO = { height: '0px', paddingTop: '0px', paddingBottom: '0px', marginTop: '0px', marginBottom: '0px', minHeight: '0px' };

  const settle = (el, a, then) => {
    if (el.__anim && el.__anim !== a) el.__anim.cancel();
    el.__anim = a;
    const done = () => { if (el.__anim === a) { el.__anim = null; el.style.overflow = el.__overflow || ''; } if (then) then(); };
    if (a) a.finished.then(done, () => {}); else done();
  };

  // Grow an element (already in the document) from nothing to its natural size.
  const enter = (el, { delay = 0, duration = 340, fade = true } = {}) => {
    if (el.__anim) el.__anim.cancel();
    const box = boxOf(el);
    el.__overflow = el.__overflow ?? el.style.overflow;
    el.style.overflow = 'hidden';
    const from = { ...ZERO, ...(fade ? { opacity: 0 } : {}) };
    const to = { ...box, minHeight: '0px', ...(fade ? { opacity: 1 } : {}) };
    settle(el, run(el, [from, to], { duration, delay }));
  };

  // Fold an element to nothing, then remove it (or hide it, for a section that may come back).
  const exit = (el, { duration = 260, keep = false } = {}) => {
    if (el.__leaving) return;
    el.__leaving = true;
    if (el.__anim) el.__anim.cancel();
    const box = boxOf(el);
    el.__overflow = el.__overflow ?? el.style.overflow;
    el.style.overflow = 'hidden';
    const a = run(el, [{ ...box, minHeight: '0px', opacity: 1 }, { ...ZERO, opacity: 0 }], { duration, fill: 'forwards' });
    settle(el, a, () => {
      if (!el.__leaving) return; // shown again meanwhile
      el.__leaving = false;
      if (a) a.cancel();
      if (keep) el.hidden = true; else el.remove();
    });
  };

  // Show or hide a section that stays in the card, folding it open or closed.
  const toggle = (el, on, opts) => {
    if (on) {
      if (el.__leaving) { el.__leaving = false; el.hidden = false; enter(el, opts); return; }
      if (!el.hidden) return;
      el.hidden = false;
      if (el.isConnected) enter(el, opts);
    } else if (!el.hidden && !el.__leaving) {
      if (el.isConnected && el.getBoundingClientRect().height > 0) exit(el, { keep: true });
      else el.hidden = true;
    }
  };

  // Plain fade, for things that keep their place (icons, chips, figures).
  const fade = (el, { delay = 0, duration = 260, y = 3, scale = 1 } = {}) =>
    run(el, [{ opacity: 0, transform: `translateY(${y}px) scale(${scale})` }, { opacity: 1, transform: 'none' }], { duration, delay });

  // Animate a size change: measure, apply the change, play the difference.
  const resize = (el, mutate, { duration = 320, axis = 'height' } = {}) => {
    const before = el.getBoundingClientRect()[axis];
    mutate();
    const after = el.getBoundingClientRect()[axis];
    if (Math.abs(after - before) < 0.5 || !el.isConnected) return;
    el.__overflow = el.__overflow ?? el.style.overflow;
    el.style.overflow = 'hidden';
    settle(el, run(el, [{ [axis]: before + 'px' }, { [axis]: after + 'px' }], { duration }));
  };

  // Decode: the new text resolves left to right out of a short run of random glyphs, the way a
  // value arrives over the wire. Spaces stay where the final text has them.
  const GLYPHS = 'abcdefghijklmnopqrstuvwxyz0123456789';
  const scramble = (s) => [...s].map((ch) => (ch === ' ' ? ' ' : GLYPHS[(Math.random() * GLYPHS.length) | 0])).join('');
  const decode = (el, text, { duration } = {}) => {
    const target = text == null ? '' : String(text);
    if (el.__target === target) return;
    el.__target = target;
    cancelAnimationFrame(el.__raf);
    if (reduced() || !target || !el.isConnected) { el.textContent = target; return; }
    const total = duration ?? Math.min(900, 240 + target.length * 22);
    const start = performance.now();
    let tail = null, lastSwap = 0, noise = '';
    // A frame's timestamp can precede `start` (it is when the frame began): clamp at 0.
    const frame = (now) => {
      const p = Math.max(0, Math.min(1, (now - start) / total));
      const shown = Math.floor((1 - (1 - p) * (1 - p)) * target.length);
      if (p >= 1 || shown >= target.length) { el.textContent = target; return; }
      const span = Math.min(target.length - shown, 2 + Math.round(6 * (1 - p)));
      if (now - lastSwap > 55 || noise.length !== span) { noise = scramble(target.slice(shown, shown + span)); lastSwap = now; }
      if (!tail || tail.parentNode !== el) { tail = document.createElement('span'); tail.className = 'gu-scramble'; }
      el.replaceChildren(document.createTextNode(target.slice(0, shown)), tail);
      tail.textContent = noise;
      el.__raf = requestAnimationFrame(frame);
    };
    el.__raf = requestAnimationFrame(frame);
  };
  // Set text without motion, cancelling a decode in flight.
  const setText = (el, text) => {
    const t = text == null ? '' : String(text);
    cancelAnimationFrame(el.__raf);
    el.__target = t;
    if (el.textContent !== t) el.textContent = t;
  };

  // Roll: the new value slides up into place, for counters and short labels.
  const roll = (el, text) => {
    const t = text == null ? '' : String(text);
    if (el.__target === t) return;
    setText(el, t);
    if (getComputedStyle(el).display === 'inline') el.style.display = 'inline-block';
    run(el, [{ opacity: 0, transform: 'translateY(60%)' }, { opacity: 1, transform: 'none' }], { duration: 280 });
  };

  // Tween: the numbers in a figure count to their new values ("15.6 / 16 GB" → "6.2 / 16 GB"),
  // when the text around them is unchanged; otherwise the new figure rolls in.
  const NUM = /-?\d+(?:[.,]\d+)?/g;
  const tween = (el, text, { duration = 750, from } = {}) => {
    const to = text == null ? '' : String(text);
    const was = from ?? el.__target ?? el.textContent;
    if (was === to && from === undefined) return;
    const a = was.match(NUM) || [], b = to.match(NUM) || [];
    const skeleton = (s) => s.replace(NUM, '#');
    if (reduced() || !el.isConnected || !b.length || a.length !== b.length || skeleton(was) !== skeleton(to)) {
      if (was === to) { setText(el, to); return; }
      roll(el, to);
      return;
    }
    cancelAnimationFrame(el.__raf);
    el.__target = to;
    const parts = to.split(NUM);
    const places = b.map((s) => (s.split(/[.,]/)[1] || '').length);
    const start = performance.now();
    const frame = (now) => {
      const p = Math.max(0, Math.min(1, (now - start) / duration));
      const e = 1 - Math.pow(1 - p, 3);
      if (p >= 1) { el.textContent = to; return; }
      let out = parts[0];
      b.forEach((s, i) => {
        const x = parseFloat(a[i].replace(',', '.')), y = parseFloat(s.replace(',', '.'));
        let v = (x + (y - x) * e).toFixed(places[i]);
        if (s.includes(',')) v = v.replace('.', ',');
        out += v + parts[i + 1];
      });
      el.textContent = out;
      el.__raf = requestAnimationFrame(frame);
    };
    el.__raf = requestAnimationFrame(frame);
  };

  // Keyed children with motion: reuse the node of each key; an item with no node may adopt a
  // leftover one (a pending row that became a commit morphs instead of being replaced); new nodes
  // grow in, leftovers fold away. update(node, item, {born, adopted, index}) paints each node.
  const keyed = (parent, items, { key, create, update, adopt, enter: onEnter, exit: onExit }) => {
    const live = [...parent.children].filter((n) => !n.__leaving && n.dataset.k !== undefined);
    const byKey = new Map(live.map((n) => [n.dataset.k, n]));
    const seen = new Map();
    const out = items.map((item, i) => {
      let k = String(key(item, i) ?? '') || `#${i}`;
      const dup = seen.get(k) || 0;
      seen.set(k, dup + 1);
      if (dup) k += `#${dup}`;
      const n = byKey.get(k) || null;
      if (n) byKey.delete(k);
      return { item, k, n, born: false, adopted: false };
    });
    const leftovers = [...byKey.values()];
    if (adopt) {
      for (const o of out) {
        if (o.n) continue;
        const i = leftovers.findIndex((n) => adopt(n, o.item));
        if (i >= 0) { o.n = leftovers.splice(i, 1)[0]; o.n.dataset.k = o.k; o.adopted = true; }
      }
    }
    let prev = null;
    for (const o of out) {
      if (!o.n) { o.n = create(o.item); o.n.dataset.k = o.k; o.born = true; }
      const want = prev ? prev.nextSibling : parent.firstChild;
      if (o.n !== want) parent.insertBefore(o.n, want);
      prev = o.n;
    }
    for (const n of leftovers) (onExit ? onExit(n) : n.remove());
    out.forEach((o, index) => update(o.n, o.item, { born: o.born, adopted: o.adopted, index }));
    if (onEnter) out.filter((o) => o.born).forEach((o, j) => onEnter(o.n, o.item, j));
    return out;
  };

  // One floating popover per container: anchors bound to it open it on hover, and moving from one
  // anchor to the next slides it across instead of closing and reopening.
  const popover = (container, cls = '') => {
    const pop = document.createElement('div');
    pop.className = `gu-pop ${cls}`.trim();
    pop.hidden = true;
    container.append(pop);
    let anchor = null, showT = 0, hideT = 0;
    const place = (a) => {
      const c = container.getBoundingClientRect(), r = a.getBoundingClientRect();
      const w = pop.offsetWidth, h = pop.offsetHeight;
      const left = Math.max(4, Math.min(r.left - c.left + r.width / 2 - w / 2, c.width - w - 4));
      let top = r.top - c.top - h - 7;
      if (top + c.top < 2) top = r.bottom - c.top + 7;
      pop.style.left = `${Math.round(left)}px`;
      pop.style.top = `${Math.round(top)}px`;
    };
    const open = (a) => {
      clearTimeout(hideT);
      const body = a.__pop();
      const nodes = (Array.isArray(body) ? body : [body]).filter(Boolean);
      if (!nodes.length) return;
      const moving = !pop.hidden && anchor && anchor !== a;
      anchor = a;
      pop.replaceChildren(...nodes);
      if (moving) { place(a); return; }
      pop.classList.add('is-still');
      pop.hidden = false;
      place(a);
      void pop.offsetWidth;
      pop.classList.remove('is-still');
      run(pop, [{ opacity: 0, transform: 'translateY(3px) scale(.985)' }, { opacity: 1, transform: 'none' }], { duration: 160 });
    };
    const close = () => {
      clearTimeout(showT);
      hideT = setTimeout(() => {
        const a = run(pop, [{ opacity: 1 }, { opacity: 0 }], { duration: 120, fill: 'forwards' });
        const end = () => { if (a) a.cancel(); pop.hidden = true; anchor = null; };
        if (a) a.finished.then(end, () => {}); else end();
      }, 140);
    };
    pop.addEventListener('mouseenter', () => clearTimeout(hideT));
    pop.addEventListener('mouseleave', close);
    return {
      bind(a, render) {
        const fresh = !a.__pop;
        a.__pop = render;
        if (!fresh) return;
        a.addEventListener('mouseenter', () => {
          clearTimeout(showT);
          clearTimeout(hideT);
          showT = setTimeout(() => open(a), pop.hidden ? 90 : 0);
        });
        a.addEventListener('mouseleave', close);
      },
      refresh() { if (anchor && !pop.hidden && anchor.isConnected) open(anchor); else if (anchor) { pop.hidden = true; anchor = null; } },
    };
  };

  // Shared look for what the kit draws itself: the decode noise, the shimmer of a busy line, the
  // popover shell. Themes colour them through --gu-* variables.
  const style = document.createElement('style');
  style.textContent = `
.gu-scramble { opacity: .45; }
.gu-shimmer {
  color: transparent; -webkit-background-clip: text; background-clip: text;
  background-image: linear-gradient(100deg, var(--gu-shimmer-base, var(--muted-foreground, #8a9099)) 0 38%,
    var(--gu-shimmer-hi, var(--foreground, #1f2328)) 50%, var(--gu-shimmer-base, var(--muted-foreground, #8a9099)) 62% 100%);
  background-size: 260% 100%; animation: gu-shimmer 1.8s linear infinite;
}
@keyframes gu-shimmer { from { background-position: 100% 0; } to { background-position: -160% 0; } }
.gu-pop { position: absolute; z-index: 20; left: 0; top: 0; max-width: min(420px, calc(100% - 8px)); pointer-events: auto;
  transition: left .2s cubic-bezier(.2,.75,.15,1), top .2s cubic-bezier(.2,.75,.15,1); }
.gu-pop.is-still { transition: none; }
.gu-pop[hidden] { display: none; }
@media (prefers-reduced-motion: reduce) { .gu-shimmer { animation: none; color: inherit; background: none; } }
`;
  (document.head || document.documentElement).append(style);

  window.GenUIMotion = Object.freeze({ EASE, reduced, run, enter, exit, toggle, fade, resize, decode, setText, roll, tween, keyed, popover });
})();
