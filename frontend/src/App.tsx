import { useCallback, useEffect, useRef, useState } from "react"
import { KeyRound, Sparkles } from "lucide-react"

import { TopBar } from "@/components/TopBar"
import { AudioStep } from "@/components/AudioStep"
import { RunSpine, type LogLine } from "@/components/RunSpine"
import { ResultView } from "@/components/ResultView"
import { SettingsSheet } from "@/components/SettingsSheet"
import { Mark } from "@/components/Mark"

import { api, bridgeReport, callWithRetry, onAppEvent, ready, usingMock } from "@/lib/api"
import { guessChrome, useWindowChrome } from "@/lib/chrome"
import { furthest, stageOf, type StageId } from "@/lib/stages"
import type { Bootstrap, KaggleStatus, RunOutcome, Settings } from "@/lib/types"
import { cn } from "@/lib/utils"

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [kaggle, setKaggle] = useState<KaggleStatus | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [fatal, setFatal] = useState("")

  const [audioFile, setAudioFile] = useState<string | null>(null)

  const [logs, setLogs] = useState<LogLine[]>([])
  const [running, setRunning] = useState(false)
  const [outcome, setOutcome] = useState<RunOutcome | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [stage, setStage] = useState<StageId | null>(null)
  const [enteredAt, setEnteredAt] = useState<Partial<Record<StageId, number>>>({})
  const [startedAt, setStartedAt] = useState(() => Date.now())

  const logId = useRef(0)

  // The bar has to be there from the first frame -- on a frameless window it
  // carries the only close button -- so it cannot wait for the bootstrap.
  const chromeKind = boot?.chrome ?? guessChrome()
  const chrome = useWindowChrome(chromeKind)

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
      if (!bridged && !usingMock()) {
        // Never carry on into the mock here: a packaged app that did would
        // show invented cues for a run that never happened.
        if (!cancelled) {
          setFatal(
            "The window opened but never connected to the Python side, so "
            + "there is nothing to transcribe with. Restarting Krevon Scribe "
            + "usually clears it.\n\n" + bridgeReport(),
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

  const reveal = useCallback((p: string) => { void api.reveal(p) }, [])

  async function pickAudio() {
    const res = await api.choose_audio_file("")
    if (res.ok && res.path) setAudioFile(res.path)
  }

  function reset() {
    setLogs([]); setOutcome(null); setRunError(null)
    setStage(null); setEnteredAt({})
  }

  async function start() {
    if (!audioFile) return
    reset()
    const now = Date.now()
    setStartedAt(now)
    setStage("upload")
    setEnteredAt({ upload: now })
    setRunning(true)
    const res = await api.start_run({ audio_file: audioFile })
    if (!res.ok) { setRunning(false); setRunError(res.error); addLog(res.error, "warn") }
  }

  const loaded = Boolean(boot && settings)
  const needsKaggle = !kaggle?.configured
  const view = outcome ? "done" : (running || runError) ? "run" : "ready"

  return (
    <div className="relative z-10 flex h-full flex-col">
      <TopBar
        chrome={chrome}
        custom={chromeKind === "custom"}
        onSettings={loaded ? () => setShowSettings(true) : undefined}
        needsSetup={needsKaggle}
      />

      {/* my-auto centres a short view without clipping a tall one, which is
          what `items-center` would do once the content overflows. */}
      <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        {fatal ? (
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
        ) : !boot || !settings ? (
          <Centered>
            <Mark size={30} className="animate-breathe" />
            <p className="mt-4 text-[12.5px] text-ink-3">Starting up…</p>
          </Centered>
        ) : (
          <div className="mx-auto my-auto w-full max-w-[600px] px-7 py-9">
            {view === "ready" && (
              <div className="animate-rise">
                <div className="mb-7">
                  <h1 className="font-display text-[26px] leading-tight text-ink">
                    Arabic and English subtitles
                  </h1>
                  <p className="mt-1.5 max-w-[48ch] text-[12.5px] leading-relaxed text-ink-3">
                    Pick an audio file and get an .srt back, with each language written in
                    its own script. Drag it onto a timeline in any editor.
                  </p>
                </div>

                <AudioStep audioFile={audioFile} onPickFile={() => void pickAudio()} />

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
                      <PrimaryButton onClick={() => void start()} disabled={!audioFile}>
                        <Sparkles className="size-4" />
                        Make subtitles
                      </PrimaryButton>
                      <p className="mt-2.5 text-[12px] text-ink-3">
                        {audioFile
                          ? "English and Arabic, in one file. Expect a few minutes."
                          : "Choose an audio file."}
                      </p>
                    </>
                  )}
                </div>
              </div>
            )}

            {view === "run" && (
              <>
                <RunSpine
                  stage={stage} enteredAt={enteredAt} startedAt={startedAt}
                  running={running} error={runError} logs={logs}
                />
                {!running && (
                  <div className="mt-7">
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
        )}
      </main>

      {settings && (
        <SettingsSheet
          open={showSettings}
          onOpenChange={setShowSettings}
          settings={settings}
          kaggle={kaggle}
          onPatch={patch}
          onKaggleSaved={(k, s) => { setKaggle(k); setSettings(s) }}
        />
      )}
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="m-auto flex flex-col items-center px-10 py-10 text-center">
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
