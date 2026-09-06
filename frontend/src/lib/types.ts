/** Mirrors resolve_subtitle_tool/config.py Settings. */
export type Settings = {
  srt_dir: string
  kaggle_username: string
  whisper_model: string
  whisper_detect_model: string
  code_switch_method: string
  code_switch_model: string
  cue_script_policy: string
  whisper_language: string
  arabic_threshold: number
  forced_alignment: boolean
  backend: string
  speechmatics_api_key: string
}

export type KaggleStatus = {
  config_dir: string
  has_env_token: boolean
  has_token_file: boolean
  has_kaggle_json: boolean
  username: string
  configured: boolean
}

export type PreviewCue = { start: number; end: number; text: string }

export type RunOutcome = {
  audio_path: string
  combined_srt: string
  en_srt: string
  ar_srt: string
  en_cues: number
  ar_cues: number
  combined_cues: number
  detected_language: string
  preview: PreviewCue[]
  preview_truncated: boolean
  warnings: string[]
}

export type Empty = Record<string, unknown>
export type Fail = { ok: false; error: string; kind?: string }
export type Ok<T> = { ok: true } & T
export type Res<T> = Ok<T> | Fail

/**
 * Who draws the title bar. "custom" means this app does, because the window is
 * frameless -- see resolve_subtitle_tool/window_chrome.py.
 */
export type ChromeKind = "custom" | "native"

/** The frameless window's controls, as window_command() names them. */
export type WindowAction =
  | "state" | "minimize" | "toggle_maximize" | "close" | "drag"

export type Bootstrap = {
  settings: Settings
  kaggle: KaggleStatus
  platform: string
  chrome: ChromeKind
  config_path: string
}

export type AppEvent =
  | { event: "log"; payload: { message: string } }
  | { event: "run_started"; payload: Empty }
  | { event: "run_finished"; payload: RunOutcome }
  | { event: "run_failed"; payload: { error: string; kind: string; traceback: string } }
