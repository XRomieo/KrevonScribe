# What is left to do

State as of the custom-title-bar work on Windows. Everything below is either
unfinished, unverified, or a decision waiting on you.

---

## 1. Bugs found in the new Windows title bar

These came out of an automated pass that drives the real window with synthetic
mouse input (`scratchpad/interact.py`). Nine checks passed, four failed. Some of
the four may be the harness rather than the app — each says which is suspected.

### 1.1 Restore after maximize comes back 16px smaller
- **Seen:** window was `1141x962`, maximized, restored → `1125x946`.
- Repeats every cycle, so the window shrinks a little each time it is maximized
  and restored.
- **Suspect:** the app, not the harness. Likely the `WS_THICKFRAME` bit added in
  `resolve_subtitle_tool/window_chrome.py::attach()` changing the frame delta
  WinForms uses when it saves and reapplies the restored bounds.
- **Fix direction:** remember the restored rect ourselves before maximizing
  (`GetWindowPlacement().rcNormalPosition`) and reapply it on restore, or add
  the style before the window is first shown rather than after.

### 1.2 Double-clicking the title bar does not maximize
- **Seen:** two clicks on an empty stretch of the bar left the window unchanged.
- **Suspect:** the app. The `onPointerDown` drag handler in
  `frontend/src/components/TopBar.tsx` starts a Python-side drag loop on the
  first click, which very likely eats the second click before React's
  `onDoubleClick` sees it.
- **Fix direction:** do the double-click detection ourselves in `onPointerDown`
  (timestamp the last press; if it was under ~400ms ago and close by, toggle
  maximize instead of starting a drag).

### 1.3 Dragging a maximized window lands it in the wrong place
- **Seen:** it *does* come out of maximized (that check passed), but the title
  bar ended up 96px below the pointer instead of under it.
- **Suspect:** the app — `_unmaximize_under_cursor()` in `window_chrome.py`.
- **Fix direction:** the vertical maths uses the maximized window rect's top,
  which is 8px above the work area; check it against the restored rect actually
  returned by `restore()`, and re-read the rect *after* WinForms has applied it
  (the call is marshalled to the UI thread, so it may not have taken effect on
  the line after).

### 1.4 Resizing by dragging the window edge did nothing
- **Seen:** dragging the right edge outward left the size unchanged.
- **Suspect:** the harness, but unconfirmed. The window definitely has the
  resize border — `WM_NCHITTEST` at the right edge returns `HTRIGHT` (11), which
  is the OS saying "this is a resize grip". Synthetic `mouse_event` input may
  not drive Windows' modal resize loop the way a real mouse does.
- **Next step:** resize it by hand once and see. If it really does not resize,
  the `WS_THICKFRAME` approach needs rethinking.

### 1.5 Re-check closing
- The final "click the close light" check never ran — the harness stopped at the
  failure above. Closing worked in earlier manual runs; it needs one clean pass.

---

## 2. Verification not yet done

- **`python scripts/build.py` has not been re-run** since the title-bar change.
  The packaged `dist/KrevonScribe/KrevonScribe.exe` on disk is from before it,
  so the frozen self-test result (13/13) predates this work too.
- **The frozen build has never been checked with the frameless window.** Running
  from source works; PyInstaller is a different path (icon, DPI manifest,
  WebView2 storage) and needs its own pass.
- **macOS is entirely unverified.** No Mac in this session. Nothing in the
  change is macOS-specific — `window_chrome.KIND` is `"native"` there and the
  window is created exactly as before — but that is reasoning, not testing.
- **A real end-to-end transcription has not been run** since the Resolve
  removal. The pipeline is covered by unit tests and the browser mock, not by an
  actual Kaggle run with real audio.

---

## 3. The macOS icon

`assets/krevon.icns` has the same defect the old `.ico` had: every pixel outside
the rounded square is **opaque white**, not transparent. It was left alone on
purpose — you said the Mac one looks fine and to change Windows only.

If you ever want it fixed, the renderer is now correct and cross-platform:

```bash
python scripts/make_icons.py --icns
```

That has to run on the Mac (`--icns` needs `iconutil`).

---

## 4. Housekeeping

- **Nothing is committed.** ~30 modified files, the staged deletion of
  `resolve_subtitle_tool/resolve_bridge.py`, and two new files
  (`resolve_subtitle_tool/window_chrome.py`, `frontend/src/lib/chrome.ts`,
  `frontend/src/components/WindowControls.tsx`, `tests/test_window_chrome.py`).
- **`README.md` does not mention the custom title bar.** It should say the
  Windows build draws its own window chrome and why, next to the icon section.
- **`docs/` still has `RESOLVE_API_FINDINGS.md` and 18 `scripts/probe_*.py`.**
  Kept deliberately as the record of why there is no editor integration, and
  linked from the README. Delete them if you would rather not carry them.
- **The package is still called `resolve_subtitle_tool`.** No user sees the
  name; renaming touches every import, `app.spec`, and the settings-migration
  path. Left as-is and documented in the README — say the word to rename it.

---

## 5. Decisions for you

- **Should the Mac get the custom title bar too?** It is roughly the same work
  (pywebview's Cocoa backend supports frameless), and it would make the two
  builds look identical. Right now macOS keeps the system title bar.
- **Traffic-light colours.** They currently use the app's own palette — amber,
  the app's green (`--go`), and the app's rose (`--pulse`) — rather than macOS's
  exact yellow/green/red. Easy to switch if you want the literal Mac look.
- **Focus dimming.** The lights grey out when the window is not focused, the way
  macOS does. It works, but it depends on the web view reporting focus; if it
  ever looks wrong, the simplest fix is to drop the dimming and keep them lit.
