import { cn } from "@/lib/utils"
import type { AudioTrack } from "@/lib/types"

export function ChannelStrip({
  track, armed, onToggle,
}: { track: AudioTrack; armed: boolean; onToggle: () => void }) {
  const empty = track.clip_count === 0
  return (
    <button
      type="button"
      role="switch"
      aria-checked={armed}
      onClick={onToggle}
      className={cn(
        "group relative flex w-full items-center gap-3 overflow-hidden rounded-md border py-2 pl-3 pr-3 text-left transition-all duration-150",
        armed
          ? "border-en/45 bg-en/[0.07]"
          : "border-line bg-panel-raised/55 hover:border-line-bright",
      )}
    >
      {/* channel arm indicator */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-0 left-0 w-[3px] transition-colors",
          armed ? "bg-en shadow-[0_0_10px_var(--en)]" : "bg-line-bright group-hover:bg-ink-faint",
        )}
      />
      <span
        className={cn(
          "ml-0.5 shrink-0 rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold tnum transition-colors",
          armed ? "bg-en/15 text-en" : "bg-panel-inset text-ink-faint",
        )}
      >
        A{track.index}
      </span>

      <span className="min-w-0 flex-1">
        <span className={cn("block truncate text-[13px] leading-tight", armed ? "text-ink" : "text-ink-dim")}>
          {track.name}
        </span>
        <span className="mt-0.5 block font-mono text-[10.5px] leading-none text-ink-faint">
          {track.sub_type || "—"} · {track.clip_count} clip{track.clip_count === 1 ? "" : "s"}
          {empty && " · empty"}
        </span>
      </span>

      {/* decorative level ladder, lit when armed */}
      <span aria-hidden className="flex shrink-0 items-end gap-[2px]" style={{ height: 16 }}>
        {[5, 9, 13, 8, 11].map((h, i) => (
          <span
            key={i}
            className={cn("w-[2px] rounded-sm transition-colors", armed ? "bg-en/65" : "bg-line-bright")}
            style={{ height: armed ? h : 4 }}
          />
        ))}
      </span>
    </button>
  )
}
