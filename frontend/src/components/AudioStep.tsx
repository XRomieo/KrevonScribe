import { FileAudio } from "lucide-react"
import { cn } from "@/lib/utils"

/** Windows and macOS disagree about separators, so split on both. */
function basename(path: string) {
  return path.split(/[\\/]/).pop() || path
}

export function AudioStep({ audioFile, onPickFile }: {
  audioFile: string | null
  onPickFile: () => void
}) {
  return (
    <section>
      <h2 className="eyebrow mb-2.5">Audio</h2>

      <button
        type="button"
        onClick={onPickFile}
        className="flex w-full items-center gap-3 rounded-lg border border-edge bg-riser/40 px-3 py-3 text-left transition-colors hover:border-edge-lit"
      >
        <FileAudio className="size-4 shrink-0 text-ink-3" />
        <span
          title={audioFile || undefined}
          className={cn(
            "min-w-0 flex-1 truncate text-[13px]",
            audioFile ? "font-mono text-ink" : "text-ink-2",
          )}
        >
          {audioFile ? basename(audioFile) : "Choose an audio file"}
        </span>
        {audioFile && <span className="shrink-0 text-[11.5px] text-ink-3">Change</span>}
      </button>

      <p className="mt-2 text-[11.5px] leading-relaxed text-ink-3">
        WAV, FLAC, MP3, M4A, AAC, OGG or Opus. Export the audio from your edit,
        or point this at the original recording.
      </p>
    </section>
  )
}
