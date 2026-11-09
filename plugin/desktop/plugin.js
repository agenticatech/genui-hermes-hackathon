// Desktop half of the genui plugin. Loaded uncompiled by Hermes Desktop: no JSX, and the
// only importable modules are @hermes/plugin-sdk, react and react/jsx-runtime.
//
// The agent's show_component returns a directive, ::genui{id="<key>"}, that the model writes as its
// own paragraph. Here that paragraph becomes a sandboxed frame running the component runtime and its
// theme. The frame is built once per component (and per host theme): every update_component reaches
// it as the plugin event `plugin.genui.component` and is posted into the same frame, which repaints
// in place. A click on a decision goes back to the agent as one user turn:
// {"type": "user_action", "component_id": "<id>", "action_id": "<id>", "values": {...}}, values
// (what the user chose in the card) only when there is something in it.
import { host, SandboxedFrame, STATUSBAR_AREAS, TRANSCRIPT_DIRECTIVE_AREA } from '@hermes/plugin-sdk'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

const KEY = /^[a-f0-9]{16}$/
const EVENT = 'plugin.genui.component'
const MIN_HEIGHT = 40
const MAX_HEIGHT = 1600
// Small on purpose: the card builds itself from its header down, and the chat grows with it.
const START_HEIGHT = 40
// The frame takes every reported height at once: the card animates its own size changes (the
// runtime's motion kit), and the frame reports each step, so the chat glides with it.

// Same theme bridge as the core ::preview directive (inline-preview-directive.tsx): the app's
// live tokens under the friendly names themes write against, plus its fonts.
const THEME_BRIDGE_TOKENS = {
  '--foreground': '--ui-text-primary',
  '--muted-foreground': '--ui-text-tertiary',
  '--accent': '--ui-accent',
  '--border': '--ui-stroke-tertiary',
  '--card': '--ui-bg-editor',
  '--host-mono': '--font-mono'
}

let pluginCtx = null

export function userActionText(componentId, actionId, values) {
  const event = { type: 'user_action', component_id: componentId, action_id: actionId }
  if (values && typeof values === 'object' && Object.keys(values).length) event.values = values
  return JSON.stringify(event)
}

// The frame's document comes whole from the backend (library.frame_document: the runtime, the
// theme, the root they draw into); the host only adds its theme prelude to the head.
const FRAME_HEAD = '<meta charset="utf-8">'
export function frameDocument(record, prelude = '') {
  const doc = String(record.document || '')
  const at = doc.indexOf(FRAME_HEAD)
  return at < 0 ? doc : doc.slice(0, at + FRAME_HEAD.length) + prelude + doc.slice(at + FRAME_HEAD.length)
}

// One shown component's link with its frame: keeps the latest props (by rev, so a late REST answer
// never undoes a newer event), posts them once the frame's theme is ready, relays clicks to the chat.
export class ComponentChannel {
  constructor({ submit, notify = () => {}, onResize = () => {} }) {
    this.submit = submit
    this.notify = notify
    this.onResize = onResize
    this.latest = null
    this.win = null
    this.ready = false
  }

  // A new frame document (the first, or a rebuild for a new host theme): wait for its ready.
  attach(win) {
    this.win = win
    this.ready = false
  }

  accept(update) {
    if (!update || typeof update.rev !== 'number' || (this.latest && update.rev <= this.latest.rev)) return false
    this.latest = { rev: update.rev, props: update.props, id: update.id }
    this.flush()
    return true
  }

  flush() {
    if (this.ready && this.win && this.latest) this.win.postMessage({ type: 'genui:props', props: this.latest.props }, '*')
  }

  handle(event) {
    if (!this.win || event.source !== this.win || !event.data) return
    const { type } = event.data
    if (type === 'genui:ready') {
      this.ready = true
      this.flush()
    } else if (type === 'genui:resize') {
      this.onResize(Number(event.data.height) || 0)
    } else if (type === 'genui:action') {
      this.deliver(String(event.data.action_id || ''), event.data.values)
    } else if (type === 'genui:error') {
      console.warn('[genui] theme error:', event.data.message)
    }
  }

  deliver(actionId, values) {
    let ok = false
    try {
      ok = Boolean(this.latest && actionId && this.submit(userActionText(this.latest.id, actionId, values)))
    } catch {}
    if (!ok) this.notify()
    this.win.postMessage({ type: 'genui:delivered', ok, action_id: actionId }, '*')
    return ok
  }
}

function colorScheme() {
  const mode = document.documentElement.dataset.hermesMode
  if (mode === 'light' || mode === 'dark') return mode
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

// The component follows the user's light or dark theme like the rest of the chat: the host's color
// scheme, tokens and fonts, on a transparent background.
function themePrelude(scheme = colorScheme()) {
  const root = getComputedStyle(document.documentElement)
  const tokens = Object.entries(THEME_BRIDGE_TOKENS)
    .map(([alias, source]) => [alias, root.getPropertyValue(source).trim()])
    .filter(([, value]) => value)
  const font = getComputedStyle(document.body).fontFamily
  if (font) tokens.push(['--host-font', font])
  return (
    `<style>:root{color-scheme:${scheme};${tokens.map(([k, v]) => `${k}:${v}`).join(';')}}` +
    `html,body{margin:0;padding:0;background:transparent;color:var(--foreground,inherit);${font ? `font-family:${font};` : ''}}</style>`
  )
}

// Theme changes repaint the app root (data-hermes-mode, class, inline tokens): bump a counter so
// the frame is rebuilt with the new tokens, as ::preview does. The props survive: they live here.
function useThemeEpoch() {
  const [epoch, setEpoch] = useState(0)
  useEffect(() => {
    const observer = new MutationObserver(() => setEpoch((n) => n + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-hermes-mode', 'data-hermes-theme'] })
    return () => observer.disconnect()
  }, [])
  return epoch
}

export function toDataUrl(html) {
  let binary = ''
  for (const byte of new TextEncoder().encode(html)) binary += String.fromCharCode(byte)
  // The charset is not optional: without it Chromium decodes the bytes as windows-1252.
  return `data:text/html;charset=utf-8;base64,${btoa(binary)}`
}

function GenuiComponent({ componentKey }) {
  const frame = useRef(null)
  const [record, setRecord] = useState(null)
  const [error, setError] = useState(null)
  const [height, setHeight] = useState(START_HEIGHT)
  // The height the frame was last given, and whether its current document has reported yet.
  const sized = useRef({ height: START_HEIGHT, reported: false })
  const themeEpoch = useThemeEpoch()

  const channel = useMemo(
    () =>
      new ComponentChannel({
        submit: (text) => host.composer.submit(null, text),
        notify: () => host.notify({ kind: 'warning', message: 'Open the chat that shows this card to send your choice to Hermes' }),
        onResize: (reported) => {
          const next = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, reported))
          sized.current = { height: next, reported: true }
          setHeight(next)
        }
      }),
    [componentKey]
  )

  // Live updates first, then the stored state: an event that lands while the fetch is in flight
  // wins over the fetch's older rev.
  useEffect(() => {
    let live = true
    const off = pluginCtx.onEvent(EVENT, (event) => {
      const update = event?.payload
      if (update && update.key === componentKey) channel.accept(update)
    })
    pluginCtx
      .rest(`/component/${componentKey}`)
      .then((loaded) => {
        if (!live) return
        channel.accept(loaded)
        setRecord(loaded)
      })
      .catch((e) => live && setError(String(e?.message || e)))
    return () => {
      live = false
      off()
    }
  }, [componentKey, channel])

  useEffect(() => {
    const onMessage = (event) => channel.handle(event)
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [channel])

  // Re-read on every repaint of the app root, but the frame is rebuilt only when the prelude
  // differs: the root's style also carries layout variables that move during scrolls and drags.
  const theme = useMemo(() => {
    const scheme = colorScheme()
    return { scheme, prelude: themePrelude(scheme) }
  }, [themeEpoch])
  // Props are not part of the document: updates never rebuild the frame.
  const src = useMemo(() => (record === null ? null : toDataUrl(frameDocument(record, theme.prelude))), [record, theme.prelude])

  // A new document waits for its runtime's ready before it gets props. A layout effect, so it
  // runs before the new document can post anything.
  useLayoutEffect(() => {
    sized.current.reported = false
    channel.attach(frame.current ? frame.current.contentWindow : null)
  }, [src, channel])

  if (error) return jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: `GenUI component unavailable: ${error}` })
  if (!src) return jsx('div', { style: { height: `${START_HEIGHT}px` } })
  return jsx(SandboxedFrame, {
    ref: frame,
    src,
    title: `GenUI ${record.type}`,
    sandbox: 'allow-scripts',
    style: {
      width: '100%',
      height: `${height}px`,
      border: 0,
      background: 'transparent',
      // Same scheme as the frame's document, or Chromium paints an opaque backdrop behind it.
      colorScheme: theme.scheme
    }
  })
}

export default {
  id: 'genui', // must match the folder name under desktop-plugins/
  name: 'GenUI',
  register(ctx) {
    pluginCtx = ctx

    ctx.register({
      id: 'component-directive',
      area: TRANSCRIPT_DIRECTIVE_AREA,
      data: {
        name: 'genui', // the agent writes ::genui{id="..."} as its own paragraph
        render: ({ attrs }) => (KEY.test(attrs?.id || '') ? jsx(GenuiComponent, { componentKey: attrs.id }) : null)
      }
    })

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 130,
      render: () =>
        jsx('button', {
          type: 'button',
          className: 'px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
          onClick: async () => {
            try {
              const pong = await ctx.rest('/ping')
              host.notify({ kind: 'info', message: `GenUI backend OK on ${pong.host}` })
            } catch (error) {
              host.notifyError(error, 'GenUI backend unavailable')
            }
          },
          children: 'genui'
        })
    })
  }
}
