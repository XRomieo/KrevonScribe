import sys
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); tl = proj.GetCurrentTimeline()
print("timeline:", tl.GetName(), "start frame:", tl.GetStartFrame())
n = tl.GetTrackCount("subtitle")
print("subtitle tracks:", n)
for i in range(1, n + 1):
    items = tl.GetItemListInTrack("subtitle", i) or []
    print(f"track {i} {tl.GetTrackName('subtitle', i)!r}: {len(items)} cues")
    for it in items:
        print(f"   start={it.GetStart()} end={it.GetEnd()} dur={it.GetDuration()} text={it.GetName()!r}")
