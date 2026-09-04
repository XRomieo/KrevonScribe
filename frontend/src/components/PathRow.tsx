import { FolderOpen } from "lucide-react"

export function PathRow({
  value, onBrowse,
}: { value: string; onBrowse: () => void }) {
  return (
    <div className="flex items-stretch gap-1.5">
      <div
        title={value}
        className="min-w-0 flex-1 truncate rounded-md border border-line bg-panel-inset px-2.5 py-[7px] font-mono text-[11px] leading-tight text-ink-dim"
      >
        {value || "—"}
      </div>
      <button
        onClick={onBrowse}
        title="Choose folder"
        className="flex shrink-0 items-center rounded-md border border-line bg-panel-raised px-2.5 text-ink-dim transition-colors hover:border-line-bright hover:text-ink"
      >
        <FolderOpen className="size-3.5" />
      </button>
    </div>
  )
}
