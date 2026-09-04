import { AlertTriangle, ArrowUpRight, Check, Hand } from "lucide-react"
import type { RunOutcome } from "@/lib/types"
import { cn } from "@/lib/utils"

function CueCard({
  lang, cues, path, placed, onReveal,
}: {
  lang: "en" | "ar"
  cues: number
  path: string
  placed: boolean
  onReveal: (p: string) => void
}) {
  const isEn = lang === "en"
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-md border px-3 py-2.5",
        isEn ? "border-en/35 bg-en/[0.055]" : "border-ar/35 bg-ar/[0.055]",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", isEn ? "bg-en" : "bg-ar")} />
      <div className="flex items-center gap-2">
        <span className={cn("font-mono text-[11px] font-semibold tracking-wider", isEn ? "text-en" : "text-ar")}>
          {isEn ? "EN" : "AR"}
        </span>
        <span className="font-mono text-[12px] tnum text-ink">{cues}</span>
        <span className="text-[11px] text-ink-faint">cue{cues === 1 ? "" : "s"}</span>
        <span
          className={cn(
            "ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium",
            placed ? "bg-live/12 text-live" : "bg-panel-inset text-ink-dim",
          )}
        >
          {placed ? <Check className="size-2.5" /> : <Hand className="size-2.5" />}
          {placed ? "On timeline" : "Media Pool"}
        </span>
      </div>
      <button
        onClick={() => onReveal(path)}
        className="group mt-1.5 flex w-full items-center gap-1 text-left font-mono text-[10.5px] text-ink-faint transition-colors hover:text-ink-dim"
      >
        <span className="truncate">{path.split("/").pop()}</span>
        <ArrowUpRight className="size-2.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
      </button>
    </div>
  )
}

export function ResultPanel({
  outcome, onReveal,
}: { outcome: RunOutcome; onReveal: (p: string) => void }) {
  return (
    <div className="space-y-2.5 animate-rise">
      <div className="flex items-baseline gap-2.5">
        <h2 className="label-etched shrink-0">Result</h2>
        <span aria-hidden className="h-px flex-1 bg-line" />
        <span className="font-mono text-[10.5px] text-ink-faint">
          detected: {outcome.detected_language}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        <CueCard
          lang="en" cues={outcome.en_cues} path={outcome.en_srt}
          placed={outcome.placed_language === "en"} onReveal={onReveal}
        />
        <CueCard
          lang="ar" cues={outcome.ar_cues} path={outcome.ar_srt}
          placed={outcome.placed_language === "ar"} onReveal={onReveal}
        />
      </div>

      {outcome.manual_srt && (
        <div className="rounded-md border border-line bg-panel-raised/60 px-3 py-2.5">
          <p className="flex items-start gap-2 text-[11.5px] leading-relaxed text-ink-dim">
            <Hand className="mt-px size-3.5 shrink-0 text-ink-faint" />
            <span>
              Drag{" "}
              <span className="font-mono text-ink">{outcome.manual_srt.split("/").pop()}</span>{" "}
              from the Media Pool onto subtitle track{" "}
              <span className="font-mono text-ink">{outcome.manual_track_index}</span>. Resolve
              routes every scripted import to the track that already holds cues, so the second
              language has to be placed by hand.
            </span>
          </p>
        </div>
      )}

      {outcome.warnings.map((w, i) => (
        <p
          key={i}
          className="flex items-start gap-2 rounded-md border border-en/25 bg-en/[0.05] px-3 py-2 text-[11.5px] leading-relaxed text-ink-dim"
        >
          <AlertTriangle className="mt-px size-3.5 shrink-0 text-en" />
          <span>{w}</span>
        </p>
      ))}
    </div>
  )
}
