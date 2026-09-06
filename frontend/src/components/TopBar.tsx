import { useRef } from "react"
import { Settings2 } from "lucide-react"

import { onControl, type WindowChrome } from "@/lib/chrome"
import { cn } from "@/lib/utils"

import { Wordmark } from "./Wordmark"
import { WindowControls } from "./WindowControls"

export function TopBar({ chrome, custom, onSettings, needsSetup }: {
  chrome: WindowChrome
  /** True when this bar is the window's title bar and has to behave like one. */
  custom: boolean
  onSettings?: () => void
  needsSetup: boolean
}) {
  // Track the last pointer-down so we can detect a double-click ourselves.
  // The drag handler starts a Python-side loop that eats the second click
  // before React's onDoubleClick ever fires.
  const lastDown = useRef<{ time: number; x: number; y: number } | null>(null)

  const drag = custom
    ? {
        onPointerDown: (e: React.PointerEvent) => {
          if (e.button !== 0 || onControl(e.target)) return
          const now = Date.now()
          const prev = lastDown.current
          if (
            prev &&
            now - prev.time < 400 &&
            Math.abs(e.clientX - prev.x) < 5 &&
            Math.abs(e.clientY - prev.y) < 5
          ) {
            // Double-click: toggle maximize instead of dragging.
            lastDown.current = null
            chrome.send("toggle_maximize")
          } else {
            lastDown.current = { time: now, x: e.clientX, y: e.clientY }
            chrome.send("drag")
          }
        },
      }
    : {}

  return (
    <header
      {...drag}
      className={cn(
        "relative z-20 flex shrink-0 items-center gap-3 border-b border-edge bg-shell/80 px-5 backdrop-blur",
        // A title bar wants a little more room, and none of it selectable.
        custom ? "select-none py-2.5 pr-3" : "py-3",
      )}
    >
      <Wordmark />

      <div className="ml-auto flex items-center gap-1">
        {onSettings && (
          <button
            type="button"
            data-no-drag
            onClick={onSettings}
            title="Settings"
            aria-label="Settings"
            className="relative flex size-8 items-center justify-center rounded-md text-ink-2 transition-colors hover:bg-riser hover:text-ink"
          >
            <Settings2 className="size-4" />
            {needsSetup && (
              <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-pulse" />
            )}
          </button>
        )}
        {custom && (
          <>
            <span aria-hidden className="mx-1.5 h-4 w-px bg-edge" />
            <WindowControls chrome={chrome} />
          </>
        )}
      </div>
    </header>
  )
}
