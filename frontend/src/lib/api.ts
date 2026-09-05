import type {
  AppEvent, Bootstrap, Empty, KaggleStatus, Res, Settings, TimelineInfo,
} from "./types"

type PyApi = {
  get_bootstrap(): Promise<Res<Bootstrap>>
  get_resolve_state(): Promise<Res<{ info: TimelineInfo }>>
  save_settings(values: Partial<Settings>): Promise<Res<{ settings: Settings }>>
  save_kaggle_credentials(v: { token?: string; username?: string; key?: string }):
    Promise<Res<{ kaggle: KaggleStatus; settings: Settings }>>
  choose_folder(current?: string): Promise<Res<{ path: string | null }>>
  choose_audio_file(current?: string): Promise<Res<{ path: string | null }>>
  reveal(path: string): Promise<Res<Empty>>
  open_external(url: string): Promise<Res<Empty>>
  start_run(options: {
    audio_source: string
    track_indices: number[]
    audio_file: string | null
    import_to_resolve: boolean
  }): Promise<Res<{ started: boolean }>>
  is_running(): Promise<Res<{ running: boolean }>>
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

export const isNative = () => typeof window.pywebview?.api !== "undefined"

/** Resolves once pywebview has injected its bridge. */
export function ready(timeoutMs = 8000): Promise<boolean> {
  if (isNative()) return Promise.resolve(true)
  return new Promise((resolve) => {
    let done = false
    const finish = (v: boolean) => { if (!done) { done = true; resolve(v) } }
    window.addEventListener("pywebviewready", () => finish(true), { once: true })
    const t0 = Date.now()
    const tick = () => {
      if (isNative()) return finish(true)
      if (Date.now() - t0 > timeoutMs) return finish(false)
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
  audio_dir: "/Users/you/Documents/Krevon Scribe/audio",
  srt_dir: "/Users/you/Documents/Krevon Scribe/srt",
  font_en: "Helvetica Neue",
  font_ar: "Geeza Pro",
  kaggle_username: "",
  whisper_model: "large-v2",
  whisper_detect_model: "large-v3",
  code_switch_method: "model",
  code_switch_model: "Seif-Eldeen-Sameh/whisper-medium-arabic-codeswitched",
  cue_script_policy: "split",
  whisper_language: "auto",
  arabic_threshold: 0.5,
  primary_language: "en",
  single_track: true,
  forced_alignment: true,
  replace_existing_subtitles: false,
  backend: "kaggle",
  speechmatics_api_key: "",
}

const mockInfo: TimelineInfo = {
  product: "DaVinci Resolve Studio", version: "21.0.0.47",
  project: "Ramadan Doc", timeline: "EP04 Rough Cut",
  fps: 24, start_frame: 86400, end_frame: 118080,
  audio_tracks: [
    { index: 1, name: "Dialogue", sub_type: "stereo", enabled: true, clip_count: 42 },
    { index: 2, name: "Interview B", sub_type: "mono", enabled: true, clip_count: 17 },
    { index: 3, name: "Music Bed", sub_type: "stereo", enabled: true, clip_count: 6 },
  ],
  subtitle_track_count: 0, populated_subtitle_tracks: [], has_content: true,
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
      ok: true, settings: mockSettings, kaggle: mockKaggle,
      resolve: { ok: true, info: mockInfo }, platform: "darwin",
      config_path: "~/Library/Application Support/Krevon Scribe/settings.json",
    }
  },
  async get_resolve_state() { return { ok: true, info: mockInfo } },
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
  async start_run() {
    void (async () => {
      emit({ event: "run_started", payload: {} })
      for (const m of [
        "Timeline 'EP04 Rough Cut' at 24 fps.",
        "Muted 1 of 3 audio tracks.",
        "Rendering audio…",
        "Rendered EP04_20260904_211500.wav.",
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
        "Wrote EP04.srt (13 cues), plus the split files.",
        "Placed 13 cues on subtitle track 1.",
      ]) { await wait(520); emit({ event: "log", payload: { message: m } }) }
      emit({
        event: "run_finished", payload: {
          audio_path: "/Users/you/Documents/Krevon Scribe/audio/EP04.wav",
          combined_srt: "/Users/you/Documents/Krevon Scribe/srt/EP04.srt",
          en_srt: "/Users/you/Documents/Krevon Scribe/srt/EP04.en.srt",
          ar_srt: "/Users/you/Documents/Krevon Scribe/srt/EP04.ar.srt",
          en_cues: 8, ar_cues: 5, combined_cues: 13,
          placed_language: "mixed", placed_cues: 13,
          manual_srt: null, manual_track_index: null, detected_language: "en",
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
          font_hint: "One track carries both languages, so it carries one font. Select the "
            + "subtitle track in Resolve and set the Inspector font to one that covers "
            + "Arabic and Latin — Geeza Pro.",
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
      const impl = (isNative() ? window.pywebview!.api : mock) as unknown as
        Record<string, (...a: unknown[]) => Promise<unknown>>
      return impl[prop](...args)
    }
  },
})
