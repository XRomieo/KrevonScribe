import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool()

path = os.path.join(SP, "captest_itt.fcpxml")
print("importing", path)
tl = mp.ImportTimelineFromFile(path, {"timelineName": "CapImportedITT"})
print("ImportTimelineFromFile ->", tl)
if not tl:
    print("FAILED"); sys.exit(1)
tl = proj.GetCurrentTimeline()
print("current timeline:", tl.GetName())
for tt in ("video", "audio", "subtitle"):
    n = tl.GetTrackCount(tt)
    print(f"  {tt}: {n} tracks")
    for i in range(1, n + 1):
        items = tl.GetItemListInTrack(tt, i) or []
        print(f"    [{i}] {tl.GetTrackName(tt,i)!r} items={len(items)}")
        if tt == "subtitle":
            for it in items:
                print("        cue:", repr(it.GetName()), "start", it.GetStart(), "dur", it.GetDuration())
