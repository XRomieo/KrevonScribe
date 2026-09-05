import { Mark } from "./Mark"

export function Wordmark() {
  return (
    <div className="flex items-center gap-2.5">
      <Mark size={20} />
      <span className="font-display text-[15px] leading-none text-ink">
        Krevon<span className="text-ink-3"> Scribe</span>
      </span>
    </div>
  )
}
