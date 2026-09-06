import type {
  AppEvent, Bootstrap, Empty, KaggleStatus, Res, Settings, WindowAction,
} from "./types"

type PyApi = {
  get_bootstrap(): Promise<Res<Bootstrap>>
  save_settings(values: Partial<Settings>): Promise<Res<{ settings: Settings }>>
  save_kaggle_credentials(v: { token?: string; username?: string; key?: string }):
    Promise<Res<{ kaggle: KaggleStatus; settings: Settings }>>
  choose_folder(current?: string): Promise<Res<{ path: string | null }>>
  choose_audio_file(current?: string): Promise<Res<{ path: string | null }>>
  reveal(path: string): Promise<Res<Empty>>
  open_external(url: string): Promise<Res<Empty>>
  start_run(options: { audio_file: string | null }): Promise<Res<{ started: boolean }>>
  is_running(): Promise<Res<{ running: boolean }>>
  window_command(action: WindowAction): Promise<Res<{ maximized: boolean }>>
}

declare global {
  interface Window {
    pywebview?: { api: PyApi }
    __appEvent?: (e: AppEvent) => void
  }
}

const listeners = new Set<(e: AppEvent) => void>()

window.__appEvent = (e: AppEvent) => {
  listeners.forEach((fn) => {
    try { fn(e) } catch { /* one bad listener must not break the rest */ }
  })
}

export function onAppEvent(fn: (e: AppEvent) => void) {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

/**
 * True only in a `bun run dev` build. Vite replaces this with a literal, so
 * everything guarded by it is dropped from the packaged bundle -- which is the
 * point: a shipped app must never be able to fall back to mock data.
 */
const DEV = import.meta.env.DEV

export const isNative = () => typeof window.pywebview !== "undefined"

/** One method that must exist before any call can be made. */
const PROBE = "get_bootstrap"

/**
 * The Python bridge, exactly as pywebview would describe it.
 *
 * pywebview creates `window.pywebview` with an empty `api` and fills it from a
 * second injected script. On Windows that second script does not always take,
 * leaving a bridge object with no methods on it and nothing to call. The
 * functions it builds only use `_jsApiCallback` and `_checkValue`, both defined
 * in the first script, so the page can build them itself from the same list.
 * tests/test_bridge_methods.py fails if this drifts from the Python class.
 */
const BRIDGE_METHODS = [
  { func: "choose_audio_file", params: ["current"] },
  { func: "choose_folder", params: ["current"] },
  { func: "get_bootstrap", params: [] },
  { func: "is_running", params: [] },
  { func: "open_external", params: ["url"] },
  { func: "reveal", params: ["path"] },
  { func: "save_kaggle_credentials", params: ["values"] },
  { func: "save_settings", params: ["values"] },
  { func: "start_run", params: ["options"] },
  { func: "window_command", params: ["action"] },
]

type PyWebview = {
  api?: Record<string, unknown>
  _createApi?: (list: { func: string; params: string[] }[]) => void
}

/** Rebuild the API when pywebview left it empty. Returns whether it worked. */
function rebuildBridge(): boolean {
  const pw = window.pywebview as unknown as PyWebview | undefined
  if (!pw || typeof pw._createApi !== "function") return false
  if (typeof pw.api?.[PROBE] === "function") return true
  try {
    pw._createApi(BRIDGE_METHODS)
  } catch {
    return false
  }
  return typeof pw.api?.[PROBE] === "function"
}

const bridgeApi = () =>
  window.pywebview?.api as Record<string, (...a: unknown[]) => Promise<unknown>> | undefined

const bridgeUsable = () => typeof bridgeApi()?.[PROBE] === "function"

/** Whether this build is answering from the mock rather than Python. */
export const usingMock = () => DEV && !bridgeUsable()

/** What the bridge looked like, for an error the user can send on. */
export function bridgeReport(): string {
  const api = bridgeApi()
  const methods = api ? Object.keys(api) : []
  return [
    `page ${window.location.protocol}//${window.location.host || "(none)"}`,
    `window.pywebview ${typeof window.pywebview}`,
    `.api ${typeof api}`,
    `methods ${methods.length ? methods.join(" ") : "none"}`,
  ].join(" · ")
}

/**
 * Resolves once the bridge can actually be called.
 *
 * pywebview's docs warn that `pywebview.api` is not ready when the page loads,
 * and neither is `window.pywebview` itself -- an earlier version of this gave
 * up on the first tick because that object was missing, and the app quietly
 * served mock data for the rest of the session. Keep polling for the whole
 * budget and let the caller decide what an absent bridge means.
 */
export function ready(timeoutMs = 20000): Promise<boolean> {
  if (bridgeUsable()) return Promise.resolve(true)
  // A dev build has no Python behind it and should reach the mock immediately.
  const budget = DEV ? 600 : timeoutMs
  return new Promise((resolve) => {
    let done = false
    const finish = (v: boolean) => { if (!done) { done = true; resolve(v) } }
    // The event can fire before the methods are attached, so it re-checks
    // rather than resolving outright; the poll below is what usually wins.
    window.addEventListener("pywebviewready", () => { if (bridgeUsable()) finish(true) })
    const t0 = Date.now()
    let rebuilt = false
    const tick = () => {
      if (bridgeUsable()) return finish(true)
      const waited = Date.now() - t0
      // Give pywebview a fair chance to finish on its own before stepping in.
      if (!rebuilt && waited > 3000) {
        rebuilt = true
        if (rebuildBridge()) return finish(true)
      }
      if (waited > budget) return finish(false)
      setTimeout(tick, 60)
    }
    tick()
  })
}

/* ---------------------------------------------------------------------------
   Browser mock. Lets the UI be built and inspected with `bun run dev`, where
   there is no Python side. Never used once pywebview injects its bridge.
   --------------------------------------------------------------------------- */
const mockSettings: Settings = {
  srt_dir: "/Users/you/Documents/Krevon Scribe",
  kaggle_username: "",
  whisper_model: "large-v2",
  whisper_detect_model: "large-v3",
  code_switch_method: "model",
  code_switch_model: "Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched",
  cue_script_policy: "split",
  whisper_language: "auto",
  arabic_threshold: 0.5,
  forced_alignment: true,
  backend: "kaggle",
  speechmatics_api_key: "",
}

const emit = (e: AppEvent) => window.__appEvent?.(e)
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

const mockKaggle: KaggleStatus = {
  config_dir: "~/.kaggle", has_env_token: false, has_token_file: false,
  has_kaggle_json: false, username: "", configured: false,
}

const mock: PyApi = {
  async get_bootstrap() {
    return {
      // The dev build previews the Windows chrome on purpose: it is the one
      // this app draws, and so the one that needs looking at in a browser.
      ok: true, settings: mockSettings, kaggle: mockKaggle, platform: "darwin",
      chrome: "custom", config_path: "~/Library/Application Support/Krevon Scribe/settings.json",
    }
  },
  async save_settings(v) { Object.assign(mockSettings, v); return { ok: true, settings: mockSettings } },
  async save_kaggle_credentials() {
    Object.assign(mockKaggle, { has_token_file: true, username: "you", configured: true })
    mockSettings.kaggle_username = "you"
    return { ok: true, kaggle: mockKaggle, settings: mockSettings }
  },
  async choose_folder() { return { ok: true, path: "/Users/you/Desktop/picked" } },
  async choose_audio_file() { return { ok: true, path: "/Users/you/Desktop/take01.wav" } },
  async reveal() { return { ok: true } },
  async open_external() { return { ok: true } },
  async is_running() { return { ok: true, running: false } },
  async window_command() { return { ok: true, maximized: false } },
  async start_run() {
    void (async () => {
      emit({ event: "run_started", payload: {} })
      for (const m of [
        "Using take01.wav.",
        "Sending to Kaggle…",
        "Uploading audio to a private Kaggle dataset…",
        "Dataset ready.",
        "Pushing the GPU kernel…",
        "Queued on Kaggle. This usually takes several minutes.",
        "Kernel status: running",
        "Kernel status: complete",
        "Downloading results…",
        "Transcribed 13 segments.",
        "Routed 8 cues to English and 5 to Arabic.",
        "Wrote take01.srt (13 cues), plus the split files.",
      ]) { await wait(520); emit({ event: "log", payload: { message: m } }) }
      emit({
        event: "run_finished", payload: {
          audio_path: "/Users/you/Desktop/take01.wav",
          combined_srt: "/Users/you/Documents/Krevon Scribe/take01.srt",
          en_srt: "/Users/you/Documents/Krevon Scribe/take01.en.srt",
          ar_srt: "/Users/you/Documents/Krevon Scribe/take01.ar.srt",
          en_cues: 8, ar_cues: 5, combined_cues: 13,
          detected_language: "en",
          preview: [
            { start: 0.0, end: 3.1, text: "Okay, so now time for the chickens." },
            { start: 3.1, end: 6.25, text: "There's a secret to chicken bath?" },
            { start: 6.25, end: 9.4, text: "بدنا نحمل ال chickens" },
            { start: 9.4, end: 11.33, text: "ال chicken bath" },
            { start: 11.33, end: 12.6, text: "Why? What's the secret?" },
            { start: 14.58, end: 18.42, text: "هيكون في مي دافية وشوي صابون" },
            { start: 18.67, end: 22.4, text: "And then we dry them off properly." },
            { start: 26.67, end: 27.38, text: "ولا شيء" },
          ],
          preview_truncated: false,
          warnings: [],
        },
      })
    })()
    return { ok: true, started: true }
  },
}

/** Reject if `p` has not settled within `ms`. */
function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`timed out after ${ms}ms`)), ms)
    p.then(
      (v) => { clearTimeout(timer); resolve(v) },
      (e) => { clearTimeout(timer); reject(e) },
    )
  })
}

/**
 * Call a bridge method, retrying calls that never settle.
 *
 * pywebview exposes `window.pywebview.api` slightly before its bridge is wired
 * up, and a call made inside that window hangs forever instead of failing. The
 * app's very first call lands exactly there, so retry rather than spin.
 */
export async function callWithRetry<T>(
  fn: () => Promise<T>, tries = 6, timeoutMs = 2000,
): Promise<T> {
  let last: unknown
  for (let i = 0; i < tries; i++) {
    try {
      return await withTimeout(fn(), timeoutMs)
    } catch (err) {
      last = err
      await new Promise((r) => setTimeout(r, 250))
    }
  }
  throw last instanceof Error ? last : new Error(String(last))
}

export const api: PyApi = new Proxy({} as PyApi, {
  get(_t, prop: string) {
    return (...args: unknown[]) => {
      // Real bridge whenever there is one. The mock is reachable only in a dev
      // build, so a packaged app fails loudly instead of inventing a timeline.
      const impl = bridgeApi()
        ?? (DEV ? (mock as unknown as Record<string, (...a: unknown[]) => Promise<unknown>>) : undefined)
      const fn = impl?.[prop]
      if (typeof fn !== "function") {
        // Minified, the bare call reads "(intermediate value)[t] is not a
        // function", which says nothing about what went wrong. Name it.
        throw new Error(`Python bridge missing ${prop}(). ${bridgeReport()}`)
      }
      return fn(...args)
    }
  },
})
