import sys
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()
start = tl.GetStartFrame()
print("timeline:", tl.GetName(), "start:", start, "end:", tl.GetEndFrame())

# clean slate: remove existing subtitle tracks, add two fresh ones
while tl.GetTrackCount("subtitle"):
    tl.DeleteTrack("subtitle", tl.GetTrackCount("subtitle"))
tl.AddTrack("subtitle"); tl.SetTrackName("subtitle", 1, "Subs EN")
tl.AddTrack("subtitle"); tl.SetTrackName("subtitle", 2, "Subs AR")
print("subtitle tracks now:", tl.GetTrackCount("subtitle"))

c = [x for x in mp.GetRootFolder().GetClipList() if x.GetClipProperty("Type") == "Subtitle"][0]
print("clip:", c.GetName())

def report(tag):
    for i in (1, 2):
        items = tl.GetItemListInTrack("subtitle", i) or []
        print(f"   {tag} track{i} ({tl.GetTrackName('subtitle',i)}): {len(items)} cues",
              [f"{it.GetStart()}" for it in items[:3]])

print("\n-- A: dict with recordFrame=start, trackIndex=1 --")
r = mp.AppendToTimeline([{"mediaPoolItem": c, "recordFrame": start, "trackIndex": 1}])
print("   ->", r); report("A")

print("\n-- B: dict with recordFrame only --")
r = mp.AppendToTimeline([{"mediaPoolItem": c, "recordFrame": start}])
print("   ->", r); report("B")

print("\n-- C: dict with trackIndex=2 only --")
r = mp.AppendToTimeline([{"mediaPoolItem": c, "trackIndex": 2}])
print("   ->", r); report("C")
