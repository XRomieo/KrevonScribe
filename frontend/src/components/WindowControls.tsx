import { useState } from "react"

import type { WindowChrome } from "@/lib/chrome"

/**
 * Minimize, maximize and close, for the builds where the window is frameless.
 *
 * Three lights rather than the system glyphs, because the bar they sit in is
 * this app's, not the OS's -- and kept on the right, where a Windows user's
 * pointer already goes for them. They carry the palette's own colours, they
 * grey out when the window loses focus, and each one shows its symbol only
 * once the pointer is somewhere in the group, which is what stops a row of
 * coloured dots reading as three status indicators.
 */
export function WindowControls({ chrome }: { chrome: WindowChrome }) {
  const [hovering, setHovering] = useState(false)
  const lit = chrome.focused || hovering

  return (
    <div
      data-no-drag
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      className="ml-1 flex items-center gap-2"
    >
      <Light
        label="Minimize" tint="var(--light-min)" lit={lit} glyph={hovering}
        onClick={() => chrome.send("minimize")}
      >
        <path d="M2 4.5h5" />
      </Light>

      <Light
        label={chrome.maximized ? "Restore" : "Maximize"}
        tint="var(--light-max)" lit={lit} glyph={hovering}
        onClick={() => chrome.send("toggle_maximize")}
      >
        {chrome.maximized ? (
          <>
            <path d="M2 3.6h3.4v3.4H2z" />
            <path d="M3.6 3.6V2H7v3.4H5.4" />
          </>
        ) : (
          <path d="M2 2h5v5H2z" />
        )}
      </Light>

      <Light
        label="Close" tint="var(--light-close)" lit={lit} glyph={hovering}
        onClick={() => chrome.send("close")}
      >
        <path d="M2.3 2.3l4.4 4.4M6.7 2.3L2.3 6.7" />
      </Light>
    </div>
  )
}

function Light({
  label, tint, lit, glyph, onClick, children,
}: {
  label: string
  tint: string
  lit: boolean
  glyph: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      // No title attribute: the OS tooltip is a white box, and having one pop
      // up over a title bar the app drew itself gives the whole thing away.
      aria-label={label}
      className="flex size-6 items-center justify-center rounded-full"
    >
      <span
        style={{ backgroundColor: lit ? tint : "var(--edge-lit)" }}
        className="flex size-3.5 items-center justify-center rounded-full shadow-[inset_0_0_0_0.5px_rgba(0,0,0,0.3)] transition-[background-color,transform] duration-150 active:scale-90"
      >
        <svg
          viewBox="0 0 9 9"
          aria-hidden
          className="size-3 transition-opacity duration-100"
          style={{
            opacity: glyph ? 1 : 0,
            stroke: "rgba(22, 8, 13, 0.65)",
            strokeWidth: 1.15,
            strokeLinecap: "round",
            strokeLinejoin: "round",
            fill: "none",
          }}
        >
          {children}
        </svg>
      </span>
    </button>
  )
}
