import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { AudioLines, FileAudio, KeyRound, Loader2, Play, Type } from "lucide-react"

import { StatusRail } from "@/components/StatusRail"
import { ChannelStrip } from "@/components/ChannelStrip"
import { Console, type LogLine } from "@/components/Console"
import { ResultPanel } from "@/components/ResultPanel"
import { KaggleDialog } from "@/components/KaggleDialog"
import { Segmented } from "@/components/Segmented"
import { PathRow } from "@/components/PathRow"
import { Section, Field } from "@/components/Section"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"

import { api, callWithRetry, onAppEvent, ready } from "@/lib/api"
import type { Bootstrap, KaggleStatus, Res, RunOutcome, Settings, TimelineInfo } from "@/lib/types"
import { cn } from "@/lib/utils"

const MODELS = ["large-v3", "large-v2", "medium", "small", "base"]
const LANGUAGES = [
  { value: "auto", label: "Auto-detect" },
  { value: "ar", label: "Arabic" },
  { value: "en", label: "English" },
]

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [kaggle, setKaggle] = useState<KaggleStatus | null>(null)
  const [resolveState, setResolveState] = useState<Res<{ info: TimelineInfo }> | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const [source, setSource] = useState<"timeline" | "file">("timeline")
  const [audioFile, setAudioFile] = useState<string | null>(null)
  const [armed, setArmed] = useState<Set<number>>(new Set())
  const [importToResolve, setImportToResolve] = useState(true)

  const [logs, setLogs] = useState<LogLine[]>([])
  const [running, setRunning] = useState(false)
  const [outcome, setOutcome] = useState<RunOutcome | null>(null)
  const [showKaggle, setShowKaggle] = useState(false)
  const [fatal, setFatal] = useState("")

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
    ;(async () => {
      await ready()
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
        if (e.event === "log") addLog(e.payload.message)
        else if (e.event === "run_started") { setRunning(true); setOutcome(null) }
        else if (e.event === "run_finished") { setRunning(false); setOutcome(e.payload) }
        else if (e.event === "run_failed") { setRunning(false); addLog(e.payload.error, "warn") }
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

  async function browse(which: "audio_dir" | "srt_dir") {
    const res = await api.choose_folder(settings?.[which] ?? "")
    if (res.ok && res.path) patch({ [which]: res.path } as Partial<Settings>)
  }

  async function pickAudio() {
    const res = await api.choose_audio_file("")
    if (res.ok && res.path) setAudioFile(res.path)
  }

  const blocker = useMemo(() => {
    if (running) return "Run in progress"
    if (!kaggle?.configured) return "Add Kaggle credentials"
    if (!settings?.kaggle_username) return "Kaggle username missing"
    if (source === "timeline") {
      if (!info) return "Resolve not connected"
      if (!info.has_content) return "Timeline is empty"
      if (armed.size === 0) return "Arm at least one audio track"
    } else if (!audioFile) return "Choose an audio file"
    return null
  }, [running, kaggle, settings, source, info, armed, audioFile])

  async function start() {
    if (blocker) return
    setLogs([]); setOutcome(null); setRunning(true)
    const res = await api.start_run({
      audio_source: source,
      track_indices: [...armed].sort((a, b) => a - b),
      audio_file: audioFile,
      import_to_resolve: importToResolve,
    })
    if (!res.ok) { setRunning(false); addLog(res.error, "warn") }
  }

  if (fatal) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-10 text-center">
        <p className="label-etched text-alert">Could not start</p>
        <p className="max-w-md font-mono text-[12px] leading-relaxed text-ink-dim">{fatal}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-1 rounded-md border border-line bg-panel-raised px-3 py-1.5 text-[11.5px] text-ink-dim transition-colors hover:border-line-bright hover:text-ink"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!boot || !settings) {
    return (
      <div className="flex h-full items-center justify-center gap-2.5 text-ink-faint">
        <Loader2 className="size-4 animate-spin" />
        <span className="font-mono text-[12px]">Connecting…</span>
      </div>
    )
  }

  return (
    <div className="relative z-10 flex h-full flex-col">
      <StatusRail state={resolveState} onRefresh={refresh} busy={refreshing} />

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(340px,400px)_1fr]">
        {/* ------------------------------ configuration ------------------ */}
        <div className="min-h-0 divide-y divide-line overflow-y-auto border-r border-line">
          <Section label="Source">
            <Segmented
              value={source}
              onChange={setSource}
              options={[
                { value: "timeline", label: "Timeline tracks" },
                { value: "file", label: "Audio file" },
              ]}
              tone="neutral"
            />

            {source === "timeline" ? (
              <div className="mt-3 space-y-1.5">
                {info ? (
                  info.audio_tracks.length ? (
                    info.audio_tracks.map((t) => (
                      <ChannelStrip
                        key={t.index}
                        track={t}
                        armed={armed.has(t.index)}
                        onToggle={() =>
                          setArmed((prev) => {
                            const next = new Set(prev)
                            next.has(t.index) ? next.delete(t.index) : next.add(t.index)
                            return next
                          })
                        }
                      />
                    ))
                  ) : (
                    <p className="py-3 text-center text-[11.5px] text-ink-faint">
                      This timeline has no audio tracks.
                    </p>
                  )
                ) : (
                  <p className="rounded-md border border-line bg-panel-inset px-3 py-3 text-[11.5px] leading-relaxed text-ink-faint">
                    Open a timeline in DaVinci Resolve, then press Refresh.
                  </p>
                )}
                {info && info.audio_tracks.length > 0 && (
                  <p className="pt-1 text-[10.5px] leading-relaxed text-ink-faint">
                    Armed tracks are mixed to one WAV. The rest are muted for the render and
                    restored afterwards.
                  </p>
                )}
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                <button
                  onClick={pickAudio}
                  className="flex w-full items-center gap-2.5 rounded-md border border-line bg-panel-inset px-3 py-2.5 text-left transition-colors hover:border-line-bright"
                >
                  <FileAudio className="size-4 shrink-0 text-ink-faint" />
                  <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-ink-dim">
                    {audioFile ? audioFile.split("/").pop() : "Choose an audio file…"}
                  </span>
                </button>
                <p className="text-[10.5px] leading-relaxed text-ink-faint">
                  File mode writes SRTs but does not import them, since the cue times are
                  relative to the file rather than to a timeline.
                </p>
              </div>
            )}
          </Section>

          <Section label="Transcription">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Model">
                <Select value={settings.whisper_model} onValueChange={(v) => patch({ whisper_model: v })}>
                  <SelectTrigger className="w-full font-mono text-[11.5px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MODELS.map((m) => (
                      <SelectItem key={m} value={m} className="font-mono text-[11.5px]">{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Spoken language">
                <Select value={settings.whisper_language} onValueChange={(v) => patch({ whisper_language: v })}>
                  <SelectTrigger className="w-full text-[11.5px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {LANGUAGES.map((l) => (
                      <SelectItem key={l.value} value={l.value} className="text-[11.5px]">{l.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
            <p className="mt-2.5 text-[10.5px] leading-relaxed text-ink-faint">
              Runs on a free Kaggle GPU. Whisper detects one language for the whole file, so
              cues are routed to tracks by inspecting their script below.
            </p>
          </Section>

          <Section label="Language routing">
            <Field label={`Arabic threshold · ${Math.round(settings.arabic_threshold * 100)}%`}>
              <Slider
                value={[settings.arabic_threshold]}
                onValueChange={([v]) => patch({ arabic_threshold: v })}
                min={0} max={1} step={0.05}
                className="py-1.5"
              />
            </Field>
            <p className="mt-1.5 text-[10.5px] leading-relaxed text-ink-faint">
              {settings.arabic_threshold <= 0.01
                ? "Any cue containing Arabic goes to the Arabic track."
                : `A cue goes to the Arabic track when at least ${Math.round(settings.arabic_threshold * 100)}% of its letters are Arabic script. Digits and punctuation are ignored.`}
            </p>

            <div className="mt-3.5">
              <Field label="Auto-place on timeline">
                <Segmented
                  value={settings.primary_language as "en" | "ar"}
                  onChange={(v) => patch({ primary_language: v })}
                  options={[{ value: "en", label: "English" }, { value: "ar", label: "Arabic" }]}
                  tone={settings.primary_language === "ar" ? "ar" : "en"}
                />
              </Field>
              <p className="mt-1.5 text-[10.5px] leading-relaxed text-ink-faint">
                Only one language can be placed automatically. The other is imported to the
                Media Pool with an empty track ready for it.
              </p>
            </div>
          </Section>

          <Section label="Fonts">
            <div className="grid grid-cols-2 gap-3">
              <Field label="English">
                <Input
                  value={settings.font_en} onChange={(e) => patch({ font_en: e.target.value })}
                  className="font-mono text-[11.5px]"
                />
              </Field>
              <Field label="Arabic">
                <Input
                  value={settings.font_ar} onChange={(e) => patch({ font_ar: e.target.value })}
                  className="font-mono text-[11.5px]"
                />
              </Field>
            </div>
            <p className="mt-2.5 flex items-start gap-1.5 text-[10.5px] leading-relaxed text-ink-faint">
              <Type className="mt-px size-3 shrink-0" />
              <span>
                Reminder only. Resolve exposes no font API, so these are set by hand on each
                subtitle track in the Inspector.
              </span>
            </p>
          </Section>

          <Section label="Destinations">
            <div className="space-y-3">
              <Field label="Rendered audio"><PathRow value={settings.audio_dir} onBrowse={() => browse("audio_dir")} /></Field>
              <Field label="Subtitles"><PathRow value={settings.srt_dir} onBrowse={() => browse("srt_dir")} /></Field>
            </div>
          </Section>

          <Section
            label="Kaggle"
            action={
              <button
                onClick={() => setShowKaggle(true)}
                className="flex items-center gap-1.5 rounded-md border border-line bg-panel-raised px-2 py-1 text-[10.5px] font-medium text-ink-dim transition-colors hover:border-line-bright hover:text-ink"
              >
                <KeyRound className="size-3" />
                {kaggle?.configured ? "Change" : "Set up"}
              </button>
            }
          >
            <div className="flex items-center gap-2.5 rounded-md border border-line bg-panel-inset px-3 py-2.5">
              <span className={cn("size-1.5 shrink-0 rounded-full", kaggle?.configured ? "bg-live" : "bg-alert")} />
              <span className="min-w-0 flex-1 font-mono text-[11px] text-ink-dim">
                {kaggle?.configured
                  ? `${kaggle.username || settings.kaggle_username || "credentials saved"}`
                  : "No credentials"}
              </span>
            </div>
            {kaggle?.configured && !settings.kaggle_username && (
              <Field label="Username">
                <Input
                  value={settings.kaggle_username}
                  onChange={(e) => patch({ kaggle_username: e.target.value })}
                  placeholder="needed to name the dataset"
                  className="mt-2.5 font-mono text-[11.5px]"
                />
              </Field>
            )}
          </Section>
        </div>

        {/* ------------------------------ console + results -------------- */}
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto p-5">
          <Console lines={logs} running={running} />
          {outcome && <ResultPanel outcome={outcome} onReveal={reveal} />}
        </div>
      </div>

      {/* ------------------------------ transport bar -------------------- */}
      <footer className="flex items-center gap-4 border-t border-line bg-panel/85 px-5 py-3 backdrop-blur hairline-top">
        <label className="flex cursor-pointer items-center gap-2.5">
          <Switch
            checked={importToResolve}
            onCheckedChange={setImportToResolve}
            disabled={source !== "timeline"}
          />
          <span className={cn("text-[11.5px]", source === "timeline" ? "text-ink-dim" : "text-ink-faint")}>
            Import back into Resolve
          </span>
        </label>

        <div className="ml-auto flex items-center gap-3">
          {blocker && !running && (
            <span className="font-mono text-[10.5px] text-ink-faint">{blocker}</span>
          )}
          <button
            onClick={start}
            disabled={!!blocker}
            className={cn(
              "group relative flex items-center gap-2.5 overflow-hidden rounded-md px-5 py-2.5 text-[12.5px] font-semibold tracking-wide transition-all duration-150",
              blocker
                ? "cursor-not-allowed border border-line bg-panel-raised text-ink-faint"
                : "bg-en text-[#1a1204] shadow-[0_0_22px_-6px_var(--en)] hover:brightness-110 active:scale-[0.985]",
            )}
          >
            {running ? (
              <>
                <Loader2 className="size-3.5 animate-spin" />
                Transcribing…
                <span aria-hidden className="absolute inset-x-0 bottom-0 h-px overflow-hidden">
                  <span className="absolute inset-y-0 w-1/3 bg-en animate-sweep" />
                </span>
              </>
            ) : (
              <>
                <Play className="size-3.5 fill-current" />
                Transcribe
                <AudioLines className="size-3.5 opacity-60" />
              </>
            )}
          </button>
        </div>
      </footer>

      <KaggleDialog
        open={showKaggle}
        onOpenChange={setShowKaggle}
        onSaved={(k, s) => { setKaggle(k); setSettings(s) }}
      />
    </div>
  )
}
