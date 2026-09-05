/** The Krevon mark. Two strokes and a stem; the rising arm carries the accent. */
export function Mark({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64" width={size} height={size} className={className}
      role="img" aria-label="Krevon"
    >
      <g fill="none" strokeLinecap="round" strokeWidth={8.5}>
        <path d="M16.5 15V49" stroke="var(--ink)" />
        <path d="M28.5 31L45 16.5" stroke="var(--pulse)" />
        <path d="M28.5 33L45 47.5" stroke="var(--ink)" />
      </g>
    </svg>
  )
}
