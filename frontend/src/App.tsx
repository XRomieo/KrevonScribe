import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { KeyRound, Sparkles } from "lucide-react"

import { TopBar } from "@/components/TopBar"
import { AudioStep } from "@/components/AudioStep"
import { RunSpine, type LogLine } from "@/components/RunSpine"
import { ResultView } from "@/components/ResultView"
import { SettingsSheet } from "@/components/SettingsSheet"
import { Mark } from "@/components/Mark"
import { Switch } from "@/components/ui/switch"

import { api, callWithRetry, isNative, onAppEvent, ready } from "@/lib/api"
import { furthest, stageOf, type StageId } from "@/lib/stages"
import type { Bootstrap, KaggleStatus, Res, RunOutcome, Settings, TimelineInfo } from "@/lib/types"
import { cn } from "@/lib/utils"

function timecode(frames: number, fps: number) {
  const f = Math.max(0, Math.round(frames))
  const r = Math.max(1, Math.round(fps))
  const p = (n: number) => String(n).padStart(2, "0")
  return `${p(Math.floor(f / (r * 3600)))}:${p(Math.floor(f / (r * 60)) % 60)}:${p(Math.floor(f / r) % 60)}`
}

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [kaggle, setKaggle] = useState<KaggleStatus | null>(null)
  const [resolveState, setResolveState] = useState<Res<{ info: TimelineInfo }> | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [fatal, setFatal] = useState("")

  const [source, setSource] = useState<"timeline" | "file">("timeline")
  const [audioFile, setAudioFile] = useState<string | null>(null)
  const [armed, setArmed] = useState<Set<number>>(new Set())
  const [importToResolve, setImportToResolve] = useState(true)

  const [logs, setLogs] = useState<LogLine[]>([])
  const [running, setRunning] = useState(false)
  const [outcome, setOutcome] = useState<RunOutcome | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [stage, setStage] = useState<StageId | null>(null)
  const [enteredAt, setEnteredAt] = useState<Partial<Record<StageId, number>>>({})
  const [startedAt, setStartedAt] = useState(() => Date.now())

  const logId = useRef(0)
  const info = resolveState?.ok ? resolveState.info : null

  const addLog = useCallback((message: string, tone: LogLine["tone"] = "info") => {
    logId.current += 1
    const time = new Date().toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    })
    setLogs((prev) => [...prev, { id: logId.current, time, message, tone }])
  }, [])

  // -- bootstrap ---------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    void (async () => {
      const bridged = await ready()
      if (!bridged && isNative()) {
        if (!cancelled) {
          setFatal(
            "The window opened but never connected to the Python side. "
            + "Closing Krevon Scribe and starting it again usually clears this.",
          )
        }
        return
      }
      let res: Awaited<ReturnType<typeof api.get_bootstrap>>
      try {
        res = await callWithRetry(() => api.get_bootstrap())
      } catch (err) {
        if (!cancelled) setFatal(err instanceof Error ? err.message : String(err))
        return
      }
      if (cancelled) return
      if (!res.ok) { setFatal(res.error); return }
      setBoot(res)
      setSettings(res.settings)
      setKaggle(res.kaggle)
      setResolveState(res.resolve)
      if (res.resolve.ok) {
        setArmed(new Set(
          res.resolve.info.audio_tracks.filter((t) => t.clip_count > 0).map((t) => t.index),
        ))
      }
    })()
    return () => { cancelled = true }
  }, [])

  // -- backend events ----------------------------------------------------
  useEffect(
    () =>
      onAppEvent((e) => {
        if (e.event === "log") {
          addLog(e.payload.message)
          const next = stageOf(e.payload.message)
          setStage((current) => {
            const moved = furthest(current, next)
            if (moved && moved !== current) {
              setEnteredAt((prev) => (prev[moved] ? prev : { ...prev, [moved]: Date.now() }))
            }
            return moved
          })
        } else if (e.event === "run_finished") {
          setRunning(false)
          setOutcome(e.payload)
        } else if (e.event === "run_failed") {
          setRunning(false)
          setRunError(e.payload.error)
          addLog(e.payload.error, "warn")
        }
      }),
    [addLog],
  )

  // -- settings persistence (debounced) ----------------------------------
  const firstSave = useRef(true)
  useEffect(() => {
    if (!settings) return
    if (firstSave.current) { firstSave.current = false; return }
    const t = setTimeout(() => { void api.save_settings(settings) }, 400)
    return () => clearTimeout(t)
  }, [settings])

  const patch = useCallback((v: Partial<Settings>) => {
    setSettings((s) => (s ? { ...s, ...v } : s))
  }, [])

  const refresh = useCallback(async () => {
    setRefreshing(true)
    const res = await api.get_resolve_state()
    setResolveState(res)
    if (res.ok) {
      setArmed((prev) => {
        const valid = new Set(res.info.audio_tracks.map((t) => t.index))
        const kept = new Set([...prev].filter((i) => valid.has(i)))
        return kept.size
          ? kept
          : new Set(res.info.audio_tracks.filter((t) => t.clip_count > 0).map((t) => t.index))
      })
    }
    setRefreshing(false)
  }, [])

  const reveal = useCallback((p: string) => { void api.reveal(p) }, [])

  const toggleArm = useCallback((index: number) => {
    setArmed((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }, [])

  async function pickAudio() {
    const res = await api.choose_audio_file("")
    if (res.ok && res.path) setAudioFile(res.path)
  }

  // `blocker` gates the button; `blockerNote` is what to say about it. They
  // differ when the page has already explained the problem twice over — a
  // missing Resolve is stated in the heading and again where the tracks go.
  const [blocker, blockerNote] = useMemo<[string | null, string | null]>(() => {
    if (source === "timeline") {
      if (!info) return ["resolve", null]
      if (!info.has_content) return ["empty", "This timeline is empty."]
      if (armed.size === 0) return ["tracks", "Tick at least one audio track."]
    } else if (!audioFile) {
      return ["file", "Choose an audio file."]
    }
    return [null, null]
  }, [source, info, armed, audioFile])

  // Resolve refuses to import onto a populated subtitle track; clearing them
  // first is the fix, and it is a setting the user has probably never seen.
  const occupiedTracks = !!runError && /already contain cues/i.test(runError)

  function reset() {
    setLogs([]); setOutcome(null); setRunError(null)
    setStage(null); setEnteredAt({})
  }

  async function start() {
    if (blocker) return
    reset()
    const now = Date.now()
    setStartedAt(now)
    setStage("render")
    setEnteredAt({ render: now })
    setRunning(true)
    const res = await api.start_run({
      audio_source: source,
      track_indices: [...armed].sort((a, b) => a - b),
      audio_file: audioFile,
      import_to_resolve: importToResolve,
    })
    if (!res.ok) { setRunning(false); setRunError(res.error); addLog(res.error, "warn") }
  }

  if (fatal) {
    return (
      <Centered>
        <Mark size={30} />
        <p className="mt-5 font-display text-[19px] text-ink">Krevon Scribe could not start</p>
        <p className="mt-2 max-w-sm font-mono text-[12px] leading-relaxed text-ink-3">{fatal}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-5 rounded-lg border border-edge px-3.5 py-2 text-[12.5px] text-ink-2 transition-colors hover:border-edge-lit hover:text-ink"
        >
          Try again
        </button>
      </Centered>
    )
  }

  if (!boot || !settings) {
    return (
      <Centered>
        <Mark size={30} className="animate-breathe" />
        <p className="mt-4 text-[12.5px] text-ink-3">Starting up…</p>
      </Centered>
    )
  }

  const needsKaggle = !kaggle?.configured
  const view = outcome ? "done" : (running || runError) ? "run" : "ready"

  return (
    <div className="relative z-10 flex h-full flex-col">
      <TopBar
        connected={!!resolveState?.ok}
        busy={refreshing}
        onRefresh={() => void refresh()}
        onSettings={() => setShowSettings(true)}
        needsSetup={needsKaggle}
      />

      {/* my-auto centres a short view without clipping a tall one, which is
          what `items-center` would do once the content overflows. */}
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div className="mx-auto my-auto w-full max-w-[600px] px-7 py-9">
          {view === "ready" && (
            <div className="animate-rise">
              {source === "file" ? (
                // The open timeline is irrelevant here, and naming it above a
                // file picker suggests a connection that does not exist.
                <div className="mb-7">
                  <h1 className="font-display text-[26px] leading-tight text-ink">
                    Transcribe a file
                  </h1>
                  <p className="mt-1.5 text-[12.5px] text-ink-3">
                    Subtitles are written next to your other exports.
                  </p>
                </div>
              ) : info ? (
                <div className="mb-7">
                  <h1 className="font-display text-[26px] leading-tight text-ink">
                    {info.timeline}
                  </h1>
                  <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-ink-3">
                    <span>{info.project}</span>
                    <Dot />
                    <span className="tnum">{info.fps.toFixed(2)} fps</span>
                    <Dot />
                    <span className="tnum">{timecode(info.end_frame - info.start_frame, info.fps)}</span>
                  </p>
                </div>
              ) : (
                <div className="mb-7">
                  <h1 className="font-display text-[26px] leading-tight text-ink">
                    Waiting for Resolve
                  </h1>
                  <p className="mt-1.5 max-w-[46ch] text-[12.5px] leading-relaxed text-ink-3">
                    {resolveState && !resolveState.ok
                      ? resolveState.error
                      : "Open a project and a timeline, then press refresh."}
                  </p>
                </div>
              )}

              <AudioStep
                source={source} onSource={setSource} info={info}
                armed={armed} onArm={toggleArm}
                audioFile={audioFile} onPickFile={() => void pickAudio()}
              />

              <div className="mt-7 border-t border-edge pt-6">
                {needsKaggle ? (
                  <>
                    <PrimaryButton onClick={() => setShowSettings(true)}>
                      <KeyRound className="size-4" />
                      Connect Kaggle
                    </PrimaryButton>
                    <p className="mt-2.5 max-w-[52ch] text-[12px] leading-relaxed text-ink-3">
                      Transcription runs on a free Kaggle GPU, so the app needs an API token
                      once. It takes a minute.
                    </p>
                  </>
                ) : (
                  <>
                    <PrimaryButton onClick={() => void start()} disabled={!!blocker}>
                      <Sparkles className="size-4" />
                      Make subtitles
                    </PrimaryButton>
                    {(() => {
                      const note = blocker
                        ? blockerNote
                        : "English and Arabic, on one subtitle track. Expect a few minutes."
                      return note && <p className="mt-2.5 text-[12px] text-ink-3">{note}</p>
                    })()}
                  </>
                )}

                {source === "timeline" && (
                  <label className="mt-5 flex cursor-pointer items-center gap-2.5">
                    <Switch checked={importToResolve} onCheckedChange={setImportToResolve} />
                    <span className="text-[12.5px] text-ink-2">Import into Resolve when done</span>
                  </label>
                )}
              </div>
            </div>
          )}

          {view === "run" && (
            <>
              <RunSpine
                stage={stage} enteredAt={enteredAt} startedAt={startedAt}
                running={running} error={runError} logs={logs}
                skip={source === "file" || !importToResolve ? ["place"] : []}
              />
              {!running && (
                <div className="mt-7 flex flex-wrap items-center gap-2.5">
                  {/* The commonest failure has exactly one fix, so offer it here
                      rather than sending the user to hunt through settings. */}
                  {occupiedTracks && (
                    <button
                      type="button"
                      onClick={() => void (async () => {
                        // Persist before starting: the debounced saver would
                        // otherwise land after the run has already read it.
                        patch({ replace_existing_subtitles: true })
                        await api.save_settings({
                          ...settings, replace_existing_subtitles: true,
                        })
                        await start()
                      })()}
                      className="rounded-lg bg-pulse px-3.5 py-2 text-[12.5px] font-semibold text-[#26060f] transition-[filter,transform] hover:brightness-110 active:scale-[0.985]"
                    >
                      Clear those tracks and run again
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={reset}
                    className="rounded-lg border border-edge px-3.5 py-2 text-[12.5px] text-ink-2 transition-colors hover:border-edge-lit hover:text-ink"
                  >
                    Back
                  </button>
                </div>
              )}
            </>
          )}

          {view === "done" && outcome && (
            <ResultView outcome={outcome} onReveal={reveal} onAgain={reset} />
          )}
        </div>
      </main>

      <SettingsSheet
        open={showSettings}
        onOpenChange={setShowSettings}
        settings={settings}
        kaggle={kaggle}
        onPatch={patch}
        onKaggleSaved={(k, s) => { setKaggle(k); setSettings(s) }}
      />
    </div>
  )
}

function Dot() {
  return <span aria-hidden className="size-[3px] rounded-full bg-edge-lit" />
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative z-10 flex h-full flex-col items-center justify-center px-10 text-center">
      {children}
    </div>
  )
}

function PrimaryButton({
  children, onClick, disabled,
}: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex items-center gap-2.5 rounded-xl px-5 py-3 text-[14px] font-semibold transition-[filter,transform,background-color] duration-150",
        disabled
          ? "cursor-not-allowed border border-edge text-ink-3"
          : "bg-pulse text-[#26060f] shadow-[0_8px_28px_-12px_var(--pulse)] hover:brightness-110 active:scale-[0.985]",
      )}
    >
      {children}
    </button>
  )
}
