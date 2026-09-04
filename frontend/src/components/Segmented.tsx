import { cn } from "@/lib/utils"

export function Segmented<T extends string>({
  value, onChange, options, tone = "en",
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  tone?: "en" | "ar" | "neutral"
}) {
  return (
    <div role="tablist" className="flex gap-1 rounded-md border border-line bg-panel-inset p-1">
      {options.map((o) => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "flex-1 rounded-[4px] px-2.5 py-1.5 text-[11.5px] font-medium transition-all duration-150",
              active
                ? tone === "ar"
                  ? "bg-ar/15 text-ar shadow-[inset_0_0_0_1px_var(--ar-dim)]"
                  : tone === "en"
                    ? "bg-en/15 text-en shadow-[inset_0_0_0_1px_var(--en-dim)]"
                    : "bg-panel-raised text-ink shadow-[inset_0_0_0_1px_var(--line-bright)]"
                : "text-ink-faint hover:text-ink-dim",
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
