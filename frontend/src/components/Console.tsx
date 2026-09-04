import { useEffect, useRef } from "react"
import { Terminal } from "lucide-react"
import { cn } from "@/lib/utils"

export type LogLine = { id: number; time: string; message: string; tone: "info" | "warn" }

export function Console({ lines, running }: { lines: LogLine[]; running: boolean }) {
  const endRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  // Follow the tail, but stop fighting the user if they scroll up to read.
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const onScroll = () => {
      pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    }
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [])

  useEffect(() => {
    if (pinned.current) endRef.current?.scrollIntoView({ block: "end" })
  }, [lines])

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line inset-well">
      <div className="flex items-center gap-2 border-b border-line/80 px-3.5 py-2">
        <Terminal className="size-3 text-ink-faint" />
        <span className="label-etched">Run log</span>
        {running && (
          <span className="relative ml-1 h-px w-10 overflow-hidden bg-line-bright">
            <span className="absolute inset-y-0 w-1/3 bg-en animate-sweep" />
          </span>
        )}
        <span className="ml-auto font-mono text-[10.5px] tnum text-ink-faint">
          {lines.length}
        </span>
      </div>

      <div ref={wrapRef} className="min-h-0 flex-1 overflow-y-auto px-3.5 py-2.5">
        {lines.length === 0 ? (
          <p className="py-6 text-center font-mono text-[11.5px] leading-relaxed text-ink-faint">
            Idle. Arm the audio tracks you want,
            <br />
            then start a run.
          </p>
        ) : (
          <ul className="space-y-[3px]">
            {lines.map((l) => (
              <li key={l.id} className="flex gap-2.5 font-mono text-[11.5px] leading-[1.55] animate-rise">
                <span className="shrink-0 tnum text-ink-faint/70">{l.time}</span>
                <span className={cn("min-w-0 break-words", l.tone === "warn" ? "text-alert" : "text-ink-dim")}>
                  {l.message}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}
