export type Settings = {
  audio_dir: string
  srt_dir: string
  font_en: string
  font_ar: string
  kaggle_username: string
  whisper_model: string
  whisper_language: string
  arabic_threshold: number
  primary_language: string
}

export type AudioTrack = {
  index: number
  name: string
  sub_type: string
  enabled: boolean
  clip_count: number
}

export type TimelineInfo = {
  product: string
  version: string
  project: string
  timeline: string
  fps: number
  start_frame: number
  end_frame: number
  audio_tracks: AudioTrack[]
  subtitle_track_count: number
  populated_subtitle_tracks: number[]
  has_content: boolean
}

export type KaggleStatus = {
  config_dir: string
  has_env_token: boolean
  has_token_file: boolean
  has_kaggle_json: boolean
  username: string
  configured: boolean
}

export type RunOutcome = {
  audio_path: string
  en_srt: string
  ar_srt: string
  en_cues: number
  ar_cues: number
  placed_language: string | null
  placed_cues: number
  manual_srt: string | null
  manual_track_index: number | null
  detected_language: string
  warnings: string[]
}

export type Empty = Record<string, unknown>
export type Fail = { ok: false; error: string; kind?: string }
export type Ok<T> = { ok: true } & T
export type Res<T> = Ok<T> | Fail

export type Bootstrap = {
  settings: Settings
  kaggle: KaggleStatus
  resolve: Res<{ info: TimelineInfo }>
  platform: string
  config_path: string
}

export type AppEvent =
  | { event: "log"; payload: { message: string } }
  | { event: "run_started"; payload: Empty }
  | { event: "run_finished"; payload: RunOutcome }
  | { event: "run_failed"; payload: { error: string; kind: string; traceback: string } }
