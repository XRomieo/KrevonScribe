import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool()
# use the real timeline that has media
for i in range(1, proj.GetTimelineCount() + 1):
    t = proj.GetTimelineByIndex(i)
    if t.GetName() == "ProbeTL2":
        proj.SetCurrentTimeline(t); break
tl = proj.GetCurrentTimeline()
print("timeline:", tl.GetName(), "subtitle tracks:", tl.GetTrackCount("subtitle"))
if tl.GetTrackCount("subtitle") == 0:
    tl.AddTrack("subtitle")

root = mp.GetRootFolder()
subs = [c for c in root.GetClipList() if c.GetClipProperty("Type") == "Subtitle"]
print("pool subtitle clips:", [c.GetName() for c in subs])
if not subs:
    sys.exit("no subtitle clip in pool")
c = subs[0]
print("clip duration prop:", c.GetClipProperty("Duration"), "frames:", c.GetClipProperty("Frames"))

variants = [
    ("plain list",        lambda: mp.AppendToTimeline([c])),
    ("varargs",           lambda: mp.AppendToTimeline(c)),
    ("dict minimal",      lambda: mp.AppendToTimeline([{"mediaPoolItem": c}])),
    ("dict mediaType3",   lambda: mp.AppendToTimeline([{"mediaPoolItem": c, "mediaType": 3, "trackIndex": 1}])),
    ("dict frames",       lambda: mp.AppendToTimeline([{"mediaPoolItem": c, "startFrame": 0, "endFrame": 167}])),
]
for name, fn in variants:
    try:
        r = fn()
    except Exception as e:
        r = f"EXC {e}"
    n = len(tl.GetItemListInTrack("subtitle", 1) or [])
    print(f"  {name:18s} -> {r!r:40s} subtitle items now: {n}")
    if n:
        print("   SUCCESS via", name); break
