import { RefreshCw, Unplug } from "lucide-react"
import type { Res, TimelineInfo } from "@/lib/types"
import { cn } from "@/lib/utils"

function timecode(frames: number, fps: number) {
  const f = Math.max(0, Math.round(frames))
  const r = Math.max(1, Math.round(fps))
  const p = (n: number) => String(n).padStart(2, "0")
  return `${p(Math.floor(f / (r * 3600)))}:${p(Math.floor(f / (r * 60)) % 60)}:${p(Math.floor(f / r) % 60)}:${p(f % r)}`
}

function Readout({ label, value, tone }: { label: string; value: string; tone?: "en" | "ar" }) {
  return (
    <div className="flex flex-col gap-0.5 px-3.5 first:pl-0">
      <span className="label-etched leading-none">{label}</span>
      <span
        className={cn(
          "font-mono text-[12.5px] leading-none tnum truncate",
          tone === "en" ? "text-en" : tone === "ar" ? "text-ar" : "text-ink",
        )}
      >
        {value}
      </span>
    </div>
  )
}

export function StatusRail({
  state, onRefresh, busy,
}: { state: Res<{ info: TimelineInfo }> | null; onRefresh: () => void; busy: boolean }) {
  const connected = !!state?.ok
  const info = state?.ok ? state.info : null

  return (
    <header className="relative z-10 flex items-center gap-1 border-b border-line bg-panel/85 px-5 py-2.5 backdrop-blur">
      <div className="flex items-center gap-2.5 pr-4">
        <span
          className={cn(
            "size-1.5 rounded-full",
            connected ? "bg-live animate-live shadow-[0_0_9px_var(--live)]" : "bg-alert",
          )}
        />
        <div className="flex flex-col gap-0.5">
          <span className="label-etched leading-none">
            {connected ? "Connected" : "Offline"}
          </span>
          <span className="font-mono text-[12.5px] leading-none text-ink">
            {info ? info.product.replace("DaVinci Resolve", "Resolve") : "DaVinci Resolve"}
          </span>
        </div>
      </div>

      {info ? (
        <div className="flex min-w-0 flex-1 items-center divide-x divide-line">
          <Readout label="Version" value={info.version} />
          <Readout label="Project" value={info.project} />
          <Readout label="Timeline" value={info.timeline} />
          <Readout label="Rate" value={`${info.fps.toFixed(2)} fps`} />
          <Readout label="Duration" value={timecode(info.end_frame - info.start_frame, info.fps)} />
        </div>
      ) : (
        <p className="flex min-w-0 flex-1 items-center gap-2 pl-4 text-[12px] text-ink-dim">
          <Unplug className="size-3.5 shrink-0 text-alert" />
          <span className="truncate">
            {state && !state.ok ? state.error : "Looking for DaVinci Resolve…"}
          </span>
        </p>
      )}

      <button
        onClick={onRefresh}
        disabled={busy}
        title="Re-read the open timeline"
        className="ml-2 flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-panel-raised px-2.5 py-1.5 text-[11px] font-medium text-ink-dim transition-colors hover:border-line-bright hover:text-ink disabled:opacity-40"
      >
        <RefreshCw className={cn("size-3", busy && "animate-spin")} />
        Refresh
      </button>
    </header>
  )
}
