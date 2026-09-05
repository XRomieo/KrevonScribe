import { useEffect, useRef, useState } from "react"
import { AlertTriangle, Check, ChevronRight } from "lucide-react"
import { STAGES, indexOf, type StageId } from "@/lib/stages"
import { cn } from "@/lib/utils"

export type LogLine = { id: number; time: string; message: string; tone: "info" | "warn" }

function clock(seconds: number) {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

/** Ticks once a second while `on`, so elapsed times stay honest. */
function useNow(on: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!on) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [on])
  return now
}

export function RunSpine({
  stage, enteredAt, startedAt, running, error, logs, skip,
}: {
  stage: StageId | null
  enteredAt: Partial<Record<StageId, number>>
  startedAt: number
  running: boolean
  error: string | null
  logs: LogLine[]
  /** Stages this run will never reach — file mode never touches Resolve. */
  skip?: StageId[]
}) {
  // null means "the user has not decided". A failure is the one time the log
  // is the thing you want, so it opens itself until they say otherwise.
  const [logOpen, setLogOpen] = useState<boolean | null>(null)
  const showLog = logOpen ?? !!error
  // The clock stops ticking when the run does, so this stays put afterwards.
  const now = useNow(running)
  const active = indexOf(stage)
  const stages = STAGES.filter((s) => !skip?.includes(s.id))
  const elapsed = now - startedAt

  return (
    <div className="animate-rise">
      <div className="mb-7 flex items-baseline gap-3">
        <span className="font-display text-[40px] leading-none tnum text-ink">
          {clock(elapsed / 1000)}
        </span>
        <span className="text-[12.5px] text-ink-3">
          {error ? "stopped" : running ? "elapsed" : "done"}
        </span>
      </div>

      <ol className="relative">
        {stages.map((s, i) => {
          const reached = active >= indexOf(s.id)
          const isActive = running && !error && s.id === stage
          const failedHere = !!error && s.id === stage
          const done = reached && !isActive && !failedHere
          const entered = enteredAt[s.id]
          const nextEntered = stages
            .slice(i + 1)
            .map((n) => enteredAt[n.id])
            .find((v): v is number => typeof v === "number")
          const took = entered ? ((nextEntered ?? now) - entered) / 1000 : null

          return (
            <li key={s.id} className="relative flex gap-3.5 pb-5 last:pb-0">
              {/* the spine */}
              {i < stages.length - 1 && (
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-[7px] top-4 -bottom-0.5 w-px",
                    reached ? "bg-edge-lit" : "bg-edge",
                  )}
                />
              )}

              <span className="relative mt-[3px] flex size-[15px] shrink-0 items-center justify-center">
                {isActive && (
                  <span aria-hidden className="absolute size-[15px] rounded-full bg-pulse/50 animate-halo" />
                )}
                <span
                  className={cn(
                    "relative flex size-[15px] items-center justify-center rounded-full border transition-colors duration-300",
                    failedHere ? "border-stop bg-stop text-[#260905]"
                      : isActive ? "border-pulse bg-pulse"
                      : done ? "border-edge-lit bg-edge-lit text-ink"
                      : "border-edge-lit bg-void",
                  )}
                >
                  {failedHere && <AlertTriangle className="size-[9px]" strokeWidth={3} />}
                  {done && <Check className="size-[9px]" strokeWidth={3.5} />}
                </span>
              </span>

              <div className="min-w-0 flex-1 pt-px">
                <div className="flex items-baseline gap-3">
                  <span
                    className={cn(
                      "text-[14px] leading-snug transition-colors",
                      failedHere ? "text-stop"
                        : isActive ? "font-medium text-ink"
                        : done ? "text-ink-2"
                        : "text-ink-3/70",
                    )}
                  >
                    {s.label}
                  </span>
                  <span aria-hidden className="h-px min-w-3 flex-1 bg-edge/70" />
                  {took !== null && (
                    <span className={cn("shrink-0 font-mono text-[11.5px] tnum", isActive ? "text-pulse" : "text-ink-3")}>
                      {clock(took)}
                    </span>
                  )}
                </div>

                {isActive && (
                  <p className="mt-1 max-w-[46ch] text-[12px] leading-relaxed text-ink-3 animate-drift">
                    {s.note}
                  </p>
                )}
                {failedHere && (
                  <p className="mt-1.5 max-w-[52ch] text-[12.5px] leading-relaxed text-stop animate-drift">
                    {error}
                  </p>
                )}
              </div>
            </li>
          )
        })}
      </ol>

      <div className="mt-6">
        <button
          type="button"
          onClick={() => setLogOpen(!showLog)}
          className="flex items-center gap-1.5 text-[12px] text-ink-3 transition-colors hover:text-ink-2"
        >
          <ChevronRight className={cn("size-3.5 transition-transform", showLog && "rotate-90")} />
          {showLog ? "Hide" : "Show"} log
          <span className="font-mono tnum">({logs.length})</span>
        </button>
        {showLog && <LogView logs={logs} />}
      </div>
    </div>
  )
}

function LogView({ logs }: { logs: LogLine[] }) {
  const endRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

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
  }, [logs])

  return (
    <div
      ref={wrapRef}
      className="mt-2.5 max-h-56 overflow-y-auto rounded-lg px-3.5 py-3 sunken animate-drift"
    >
      {logs.length === 0 ? (
        <p className="font-mono text-[11.5px] text-ink-3">Nothing yet.</p>
      ) : (
        <ul className="space-y-1">
          {logs.map((l) => (
            <li key={l.id} className="flex gap-2.5 font-mono text-[11.5px] leading-[1.6]">
              <span className="shrink-0 tnum text-ink-3/70">{l.time}</span>
              <span className={cn("min-w-0 break-words", l.tone === "warn" ? "text-stop" : "text-ink-2")}>
                {l.message}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div ref={endRef} />
    </div>
  )
}
