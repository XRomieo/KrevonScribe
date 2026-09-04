"""Stage 1 probe: connect to Resolve and report what's available. Read-only."""
import sys, os, importlib.util

MODULE_PATHS = [
    "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
    os.path.expandvars(r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"),
]
for p in MODULE_PATHS:
    if os.path.isdir(p):
        sys.path.insert(0, p)

import DaVinciResolveScript as dvr

resolve = dvr.scriptapp("Resolve")
if resolve is None:
    print("FAIL: scriptapp('Resolve') returned None. Is Resolve running with external scripting enabled?")
    sys.exit(1)

print("OK connected")
print("  GetProductName :", resolve.GetProductName())
print("  GetVersionString:", resolve.GetVersionString())
print("  GetCurrentPage :", resolve.GetCurrentPage())

pm = resolve.GetProjectManager()
print("  ProjectManager :", pm)
print("  CurrentDatabase:", pm.GetCurrentDatabase())
print("  ProjectsInFolder:", pm.GetProjectListInCurrentFolder())

proj = pm.GetCurrentProject()
print("  CurrentProject :", proj.GetName() if proj else None)
if proj:
    print("  TimelineCount  :", proj.GetTimelineCount())
    tl = proj.GetCurrentTimeline()
    print("  CurrentTimeline:", tl.GetName() if tl else None)
    if tl:
        for tt in ("video", "audio", "subtitle"):
            n = tl.GetTrackCount(tt)
            names = [tl.GetTrackName(tt, i) for i in range(1, n + 1)]
            print(f"    {tt:9s} tracks: {n} {names}")
