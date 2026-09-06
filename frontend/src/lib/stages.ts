/**
 * Turns the backend's log stream into named stages.
 *
 * A run takes several minutes on someone else's GPU, and the only questions a
 * user has while waiting are "where is it" and "is it stuck". A scrolling log
 * answers both badly, so the log lines are matched against the messages the
 * pipeline actually emits and collapsed into four stages.
 *
 * Matching is deliberately loose and the result is monotonic: an unrecognised
 * line leaves the stage where it was, and nothing ever moves backwards.
 */

export type StageId = "upload" | "queue" | "transcribe" | "cues"

export type Stage = {
  id: StageId
  label: string
  /** Shown under the label while this stage is the active one. */
  note: string
  patterns: RegExp[]
}

export const STAGES: Stage[] = [
  {
    id: "upload",
    label: "Upload",
    note: "Sending the audio to a private dataset.",
    patterns: [
      /^using /i, /sending to kaggle/i, /uploading .*(kaggle|dataset|speechmatics)/i,
      /^staging /i, /^dataset (ready|still processing)/i,
    ],
  },
  {
    id: "queue",
    label: "Wait for a GPU",
    note: "Kaggle queues free GPUs. This is usually the longest wait.",
    patterns: [
      /pushing the gpu kernel/i, /queued on kaggle/i,
      /kernel status: (queued|preparing)/i, /^job .* submitted/i,
    ],
  },
  {
    id: "transcribe",
    label: "Transcribe and align",
    note: "One code-switch pass, then the timings are measured against the audio.",
    patterns: [
      /kernel status: (running|complete)/i, /downloading results/i,
      /^transcribed /i, /speechmatics job/i, /melia tagged/i, /whisper reported/i,
    ],
  },
  {
    id: "cues",
    label: "Write the subtitles",
    note: "Separating the two scripts and writing the .srt files.",
    patterns: [/^routed \d+ cues/i, /^wrote /i],
  },
]

const ORDER = new Map(STAGES.map((s, i) => [s.id, i]))

/** The stage a log line belongs to, or null if it belongs to none. */
export function stageOf(message: string): StageId | null {
  for (const stage of STAGES) {
    if (stage.patterns.some((p) => p.test(message))) return stage.id
  }
  return null
}

/** Advance `current` if `next` is further along; never move backwards. */
export function furthest(current: StageId | null, next: StageId | null): StageId | null {
  if (!next) return current
  if (!current) return next
  return (ORDER.get(next) ?? 0) > (ORDER.get(current) ?? 0) ? next : current
}

export function indexOf(id: StageId | null): number {
  return id ? (ORDER.get(id) ?? -1) : -1
}
