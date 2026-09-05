import { RefreshCw, Settings2 } from "lucide-react"
import { Wordmark } from "./Wordmark"
import { cn } from "@/lib/utils"

export function TopBar({
  connected, busy, onRefresh, onSettings, needsSetup,
}: {
  connected: boolean
  busy: boolean
  onRefresh: () => void
  onSettings: () => void
  needsSetup: boolean
}) {
  return (
    <header className="relative z-20 flex shrink-0 items-center gap-3 border-b border-edge bg-shell/80 px-5 py-3 backdrop-blur">
      <Wordmark />

      <span
        className={cn(
          "ml-2 flex items-center gap-2 rounded-full border px-2.5 py-1 text-[11.5px] leading-none",
          connected
            ? "border-go/25 bg-go/[0.07] text-go"
            : "border-edge bg-riser text-ink-3",
        )}
      >
        <span className={cn("size-1.5 rounded-full", connected ? "bg-go" : "bg-ink-3")} />
        {connected ? "Resolve connected" : "Resolve not found"}
      </span>

      <div className="ml-auto flex items-center gap-1">
        <IconButton label="Re-read the open timeline" onClick={onRefresh} disabled={busy}>
          <RefreshCw className={cn("size-4", busy && "animate-spin")} />
        </IconButton>
        <IconButton label="Settings" onClick={onSettings}>
          <Settings2 className="size-4" />
          {needsSetup && (
            <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-pulse" />
          )}
        </IconButton>
      </div>
    </header>
  )
}

function IconButton({
  children, label, onClick, disabled,
}: {
  children: React.ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="relative flex size-8 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-riser hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  )
}
