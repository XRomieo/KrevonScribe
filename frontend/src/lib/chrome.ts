import { useCallback, useEffect, useState } from "react"

import { api } from "./api"
import type { ChromeKind, WindowAction } from "./types"

/**
 * What the title bar will be, before Python has said.
 *
 * The real answer is `chrome` on the bootstrap, but that arrives over the
 * bridge, and the first seconds of the app -- the splash, and the screen shown
 * when the bridge never connects at all -- happen before it. Guessing is safe
 * here rather than a duplicate rule: window_chrome.py decides on
 * `sys.platform == "win32"`, and the page is running on that same machine.
 */
export function guessChrome(): ChromeKind {
  return /windows/i.test(navigator.userAgent) ? "custom" : "native"
}

export type WindowChrome = {
  /** True while this window is the one the user is working in. */
  focused: boolean
  maximized: boolean
  send: (action: WindowAction) => void
}

/** Drives a frameless window's own title bar. Inert when the OS draws one. */
export function useWindowChrome(kind: ChromeKind): WindowChrome {
  const custom = kind === "custom"
  const [maximized, setMaximized] = useState(false)
  const [focused, setFocused] = useState(true)

  const send = useCallback((action: WindowAction) => {
    if (!custom) return
    void (async () => {
      try {
        const res = await api.window_command(action)
        if (res.ok) setMaximized(res.maximized)
      } catch { /* the window going away mid-call is not worth reporting */ }
    })()
  }, [custom])

  useEffect(() => {
    if (!custom) return
    send("state")
    // Snapping, Win+Up and a double-click on the bar all change the state
    // without going through our buttons, and every one of them resizes the
    // page. Debounced because a drag on the resize border fires constantly.
    let timer: ReturnType<typeof setTimeout>
    const onResize = () => {
      clearTimeout(timer)
      timer = setTimeout(() => send("state"), 160)
    }
    const onFocus = () => setFocused(true)
    const onBlur = () => setFocused(false)
    window.addEventListener("resize", onResize)
    window.addEventListener("focus", onFocus)
    window.addEventListener("blur", onBlur)
    return () => {
      clearTimeout(timer)
      window.removeEventListener("resize", onResize)
      window.removeEventListener("focus", onFocus)
      window.removeEventListener("blur", onBlur)
    }
  }, [custom, send])

  return { focused, maximized, send }
}

/** True when the event started on something that is not the bar itself. */
export function onControl(target: EventTarget | null): boolean {
  return target instanceof Element && !!target.closest("[data-no-drag]")
}
