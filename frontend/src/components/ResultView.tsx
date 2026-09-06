import { useCallback, useEffect, useRef, useState } from "react"
import { AlertTriangle, Check, FolderOpen, MousePointerClick } from "lucide-react"
import type { PreviewCue, RunOutcome } from "@/lib/types"
import { cn } from "@/lib/utils"

// Every Unicode block that carries Arabic script, mirroring subtitle_utils.py.
const ARABIC = /[؀-ۿݐ-ݿࡰ-࢟ࢠ-ࣿﭐ-﷿ﹰ-﻿]/

/** True when the cue is mostly Arabic, so it needs an RTL line. */
function isArabic(text: string) {
  const letters = [...text].filter((c) => /\p{L}/u.test(c))
  if (!letters.length) return false
  return letters.filter((c) => ARABIC.test(c)).length / letters.length >= 0.5
}

/** Windows and macOS disagree about separators, so split on both. */
function basename(path: string) {
  return path.split(/[\\/]/).pop() || path
}

/** The folder holding the file, for saying where the subtitles went. */
function dirname(path: string) {
  const cut = path.search(/[\\/][^\\/]*$/)
  return cut > 0 ? path.slice(0, cut) : path
}

function stamp(seconds: number) {
  const s = Math.max(0, seconds)
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`
}

function CueRow({ cue }: { cue: PreviewCue }) {
  const rtl = isArabic(cue.text)
  return (
    <li className="flex gap-3.5 px-3.5 py-2 transition-colors hover:bg-riser/40">
      <span className="w-9 shrink-0 pt-px font-mono text-[11px] tnum text-ink-3">
        {stamp(cue.start)}
      </span>
      <span
        dir={rtl ? "rtl" : "ltr"}
        className={cn("min-w-0 flex-1 text-[13px] leading-relaxed text-ink-2", rtl && "rtl")}
      >
        {cue.text}
      </span>
    </li>
  )
}

/** True while the list has content below the fold, so the fade earns its place. */
function useMoreBelow<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [more, setMore] = useState(false)
  // Returned as a tuple: reading `.ref` off an object in JSX reads to lint
  // rules (and to a reader) like touching a ref during render.
  const measure = useCallback(() => {
    const el = ref.current
    if (!el) return
    setMore(el.scrollHeight - el.scrollTop - el.clientHeight > 4)
  }, [])
  useEffect(() => {
    const el = ref.current
    if (!el) return
    measure()
    el.addEventListener("scroll", measure, { passive: true })
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => { el.removeEventListener("scroll", measure); observer.disconnect() }
  }, [measure])
  return [ref, more] as const
}

export function ResultView({
  outcome, onReveal, onAgain,
}: { outcome: RunOutcome; onReveal: (p: string) => void; onAgain: () => void }) {
  const [listRef, moreBelow] = useMoreBelow<HTMLUListElement>()
  const bothLanguages = outcome.en_cues > 0 && outcome.ar_cues > 0
  return (
    <div className="animate-rise">
      <div className="mb-6 flex items-start gap-3">
        <span className="mt-1 flex size-5 shrink-0 items-center justify-center rounded-full bg-go/15 text-go">
          <Check className="size-3" strokeWidth={3.5} />
        </span>
        <div>
          <h2 className="font-display text-[22px] leading-tight text-ink">
            {outcome.combined_cues} subtitles ready
          </h2>
          <p className="mt-1 text-[12.5px] text-ink-3">
            {outcome.en_cues} English · {outcome.ar_cues} Arabic
          </p>
        </div>
      </div>

      {outcome.preview.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-edge bg-shell/60">
          <div className="relative">
            <ul ref={listRef} className="max-h-72 divide-y divide-edge/60 overflow-y-auto">
              {outcome.preview.map((c, i) => <CueRow key={i} cue={c} />)}
            </ul>
            {moreBelow && (
              <span
                aria-hidden
                className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-shell to-transparent"
              />
            )}
          </div>
          {outcome.preview_truncated && (
            <p className="border-t border-edge px-3.5 py-2 text-[11.5px] text-ink-3">
              First {outcome.preview.length} cues. The file holds all {outcome.combined_cues}.
            </p>
          )}
        </div>
      )}

      {/* The one thing left to do, and it is the same in every editor. */}
      <div className="mt-3.5 rounded-xl border border-pulse/25 bg-pulse/[0.05] px-4 py-3.5">
        <p className="flex items-center gap-2 text-[12.5px] font-medium text-pulse">
          <MousePointerClick className="size-3.5" />
          Drag it onto your timeline
        </p>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-2">
          <span className="font-mono text-ink">{basename(outcome.combined_srt)}</span> holds
          both languages in time order. It is plain SRT, so Resolve, Premiere, Final Cut and
          CapCut all take it the same way — drop it on a subtitle track.
          {bothLanguages && (
            <> One track carries one font, so pick one that covers Arabic and Latin: Noto Sans
            Arabic, Geeza Pro on macOS, Dubai on Windows.</>
          )}
        </p>
        {bothLanguages && (
          <p className="mt-2 text-[11.5px] leading-relaxed text-ink-3">
            Want a font for each language? <span className="font-mono">{basename(outcome.en_srt)}</span>{" "}
            and <span className="font-mono">{basename(outcome.ar_srt)}</span> are the same cues
            split in two, for a track each.
          </p>
        )}
      </div>

      {outcome.warnings.map((w, i) => (
        <p
          key={i}
          className="mt-3.5 flex items-start gap-2.5 rounded-xl border border-stop/25 bg-stop/[0.05] px-4 py-3 text-[12.5px] leading-relaxed text-ink-2"
        >
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-stop" />
          <span>{w}</span>
        </p>
      ))}

      <div className="mt-5 flex flex-wrap items-center gap-2.5">
        <button
          type="button"
          onClick={() => onReveal(outcome.combined_srt)}
          className="flex items-center gap-2 rounded-lg bg-pulse px-4 py-2.5 text-[13px] font-semibold text-[#26060f] transition-[filter,transform] duration-150 hover:brightness-110 active:scale-[0.985]"
        >
          <FolderOpen className="size-3.5" />
          Open folder
        </button>
        <button
          type="button"
          onClick={onAgain}
          className="rounded-lg border border-edge px-3.5 py-2.5 text-[13px] text-ink-2 transition-colors hover:border-edge-lit hover:text-ink"
        >
          Transcribe another
        </button>
      </div>

      {/* Where it went, and what the button will do -- the folder opens with
          the file already picked out, so it can be dragged straight from there. */}
      <p className="mt-3 text-[11.5px] leading-relaxed text-ink-3">
        Saved in{" "}
        <span className="font-mono text-ink-2">{dirname(outcome.combined_srt)}</span>.
        Opening the folder selects the file, ready to drag.
      </p>
    </div>
  )
}
