import { cn } from "@/lib/utils"

export function Section({
  label, hint, children, className, action,
}: {
  label: string
  hint?: string
  children: React.ReactNode
  className?: string
  action?: React.ReactNode
}) {
  return (
    <section className={cn("px-5 py-4", className)}>
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2.5 min-w-0">
          <h2 className="label-etched shrink-0">{label}</h2>
          <span aria-hidden className="h-px flex-1 min-w-4 bg-line" />
        </div>
        {action}
      </header>
      {hint && <p className="-mt-1 mb-3 text-[11px] leading-relaxed text-ink-faint">{hint}</p>}
      {children}
    </section>
  )
}

export function Field({
  label, children, htmlFor,
}: { label: string; children: React.ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="label-etched block">{label}</label>
      {children}
    </div>
  )
}
