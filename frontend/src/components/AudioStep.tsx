import { Check, FileAudio, Music4 } from "lucide-react"
import type { AudioTrack, TimelineInfo } from "@/lib/types"
import { cn } from "@/lib/utils"

export function Toggle<T extends string>({
  value, onChange, options,
}: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[] }) {
  return (
    <div role="tablist" className="flex gap-0.5 rounded-md border border-edge bg-sink p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          type="button"
          aria-selected={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-[5px] px-2.5 py-1 text-[11.5px] font-medium transition-colors duration-150",
            o.value === value
              ? "bg-riser text-ink shadow-[inset_0_0_0_1px_var(--edge-lit)]"
              : "text-ink-3 hover:text-ink-2",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function TrackRow({
  track, armed, onToggle,
}: { track: AudioTrack; armed: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={armed}
      onClick={onToggle}
      className={cn(
        "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors duration-150",
        armed
          ? "border-edge-lit bg-riser"
          : "border-edge bg-riser/25 hover:border-edge-lit",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex size-[18px] shrink-0 items-center justify-center rounded-[5px] border transition-colors",
          armed ? "border-pulse bg-pulse text-[#26060f]" : "border-edge-lit",
        )}
      >
        {armed && <Check className="size-3" strokeWidth={3} />}
      </span>

      <span className={cn("shrink-0 font-mono text-[11.5px] tnum", armed ? "text-ink-2" : "text-ink-3")}>
        A{track.index}
      </span>

      <span className={cn("min-w-0 flex-1 truncate text-[13.5px]", armed ? "text-ink" : "text-ink-2")}>
        {track.name}
      </span>

      <span className="shrink-0 text-[11.5px] tnum text-ink-3">
        {track.clip_count === 0 ? "empty" : `${track.clip_count} clip${track.clip_count === 1 ? "" : "s"}`}
      </span>
    </button>
  )
}

export function AudioStep({
  source, onSource, info, armed, onArm, audioFile, onPickFile,
}: {
  source: "timeline" | "file"
  onSource: (v: "timeline" | "file") => void
  info: TimelineInfo | null
  armed: Set<number>
  onArm: (index: number) => void
  audioFile: string | null
  onPickFile: () => void
}) {
  return (
    <section>
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <h2 className="eyebrow">Audio</h2>
        <Toggle
          value={source}
          onChange={onSource}
          options={[{ value: "timeline", label: "Timeline" }, { value: "file", label: "File" }]}
        />
      </div>

      {source === "timeline" ? (
        info?.audio_tracks.length ? (
          <div className="space-y-1.5">
            {info.audio_tracks.map((t) => (
              <TrackRow
                key={t.index} track={t} armed={armed.has(t.index)}
                onToggle={() => onArm(t.index)}
              />
            ))}
            <p className="pt-1 text-[11.5px] leading-relaxed text-ink-3">
              Ticked tracks are mixed into one file. The rest are muted for the render and
              switched back on afterwards.
            </p>
          </div>
        ) : (
          <Empty icon={<Music4 className="size-4" />}>
            {info
              ? "This timeline has no audio tracks."
              : "Open a timeline in DaVinci Resolve, then press refresh."}
          </Empty>
        )
      ) : (
        <div className="space-y-2">
          <button
            type="button"
            onClick={onPickFile}
            className="flex w-full items-center gap-3 rounded-lg border border-edge bg-riser/40 px-3 py-3 text-left transition-colors hover:border-edge-lit"
          >
            <FileAudio className="size-4 shrink-0 text-ink-3" />
            <span className={cn("min-w-0 flex-1 truncate text-[13px]", audioFile ? "font-mono text-ink" : "text-ink-2")}>
              {audioFile ? audioFile.split("/").pop() : "Choose an audio file"}
            </span>
          </button>
          <p className="text-[11.5px] leading-relaxed text-ink-3">
            A file is transcribed to subtitle files on disk, but not imported: its cue times
            are relative to the file, not to your timeline.
          </p>
        </div>
      )}
    </section>
  )
}

function Empty({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-2.5 rounded-lg border border-dashed border-edge px-3.5 py-4 text-[12.5px] text-ink-3">
      <span className="shrink-0">{icon}</span>
      {children}
    </p>
  )
}
