// GenUI component runtime: runs inside the sandboxed frame that shows one component, after the
// motion kit (motion.js) and ahead of its theme. The frame has an opaque origin, so postMessage to
// the Desktop half is its only way out.
//   host → frame  {type: 'genui:props', props}           paint (the first) or repaint (every update)
//                 {type: 'genui:delivered', ok, action_id}  the decision reached the chat, or not
//   frame → host  {type: 'genui:ready'}                   the theme is loaded: send the props
//                 {type: 'genui:action', action_id, values}  the user clicked a decision; values is
//                                                         what they chose in the card (see collect)
//                 {type: 'genui:resize', height}          where the content ends, so the frame fits it
//                 {type: 'genui:open', url}               the user clicked an http(s) link: the host
//                                                         opens it in their browser (no popups here)
//                 {type: 'genui:error', message}          the theme threw
// A theme registers GenUI.register(type, (root, props, emit) => ...) and gets the same root on every
// paint, so it can update nodes in place instead of rebuilding the card; GenUI.motion animates
// those updates.
(() => {
  const post = (msg) => parent.postMessage(msg, '*');
  const themes = {};
  window.GenUI = Object.freeze({ register: (type, draw) => { themes[type] = draw; }, motion: window.GenUIMotion });

  let root = null;
  let pending = null;
  // What the user chose, read from every element the theme marked data-field="<name>": the checked
  // checkboxes of a field become a list of their values, a range or number input a number, anything
  // else its value. Same rules as the benchmark's host.
  const collect = () => {
    const v = {};
    for (const f of root.querySelectorAll('[data-field]')) {
      const k = f.dataset.field;
      if (f.type === 'checkbox') { (v[k] = v[k] || []); if (f.checked) v[k].push(f.value); }
      else if (f.type === 'radio') { if (f.checked) v[k] = f.value; else if (!(k in v)) v[k] = null; }
      else if (f.type === 'range' || f.type === 'number') v[k] = f.value === '' ? null : Number(f.value);
      else v[k] = f.value;
    }
    return v;
  };
  const emit = (actionId, extra) =>
    post({ type: 'genui:action', action_id: String(actionId), values: Object.assign(root ? collect() : {}, extra || {}) });
  const paint = (props) => {
    if (!root) { pending = props; return; }
    const draw = themes[root.dataset.type];
    if (!draw) { post({ type: 'genui:error', message: 'no theme registered for ' + root.dataset.type }); return; }
    try { draw(root, props, emit); }
    catch (e) { console.error(e); post({ type: 'genui:error', message: String((e && e.stack) || e) }); }
  };

  // The frame's sandbox has no popups (the SDK refuses them), so a link cannot open from here: its
  // click goes to the host, which opens http(s) links in the user's browser.
  addEventListener('click', (e) => {
    const a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
    if (!a) return;
    e.preventDefault();
    if (/^https?:\/\//i.test(a.href)) post({ type: 'genui:open', url: a.href });
  });

  addEventListener('message', (e) => {
    if (e.source !== parent || !e.data) return;
    if (e.data.type === 'genui:props') paint(e.data.props || {});
    // A decision that did not reach the chat (no visible composer) can be clicked again.
    if (e.data.type === 'genui:delivered' && e.data.ok === false && root) {
      for (const b of root.querySelectorAll('[data-action]')) if (b.dataset.action === e.data.action_id) b.disabled = false;
    }
  });

  // Height = where the content ends, not scrollHeight: the root's scrollHeight never drops below the
  // frame's own height, so the frame could grow but never shrink. Layout offsets ignore transforms,
  // so entrance motion does not wobble the frame; height animations do move it, step by step.
  const px = (v) => parseFloat(v) || 0;
  const measure = () => {
    const b = document.body;
    let h = 0;
    for (const el of b.children) {
      if (el.offsetParent === null && getComputedStyle(el).position !== 'fixed') continue;
      h = Math.max(h, el.offsetTop + el.offsetHeight + px(getComputedStyle(el).marginBottom));
    }
    const cs = getComputedStyle(b);
    return Math.ceil(h + px(cs.paddingBottom) + px(cs.borderBottomWidth) + px(cs.marginBottom));
  };
  let last = -1, queued = false;
  const report = () => {
    queued = false;
    const h = measure();
    if (h !== last) { last = h; post({ type: 'genui:resize', height: h }); }
  };
  // A timer, not a frame callback: Chromium pauses frames in an off-screen frame, and the chat
  // still needs the right height to lay out the messages around it.
  const queue = () => { if (!queued) { queued = true; setTimeout(report, 0); } };

  addEventListener('DOMContentLoaded', () => {
    root = document.getElementById('genui-root');
    // The frame is sized to the card: a scrollbar could only flash for the frame or two the host
    // takes to follow a card that grows.
    document.documentElement.style.overflow = 'hidden';
    try { new ResizeObserver(queue).observe(root); } catch {}
    try { new MutationObserver(queue).observe(root, { childList: true, subtree: true, attributes: true, characterData: true }); } catch {}
    if (pending) { const p = pending; pending = null; paint(p); }
    report();
    post({ type: 'genui:ready' });
  }, { once: true });
})();
