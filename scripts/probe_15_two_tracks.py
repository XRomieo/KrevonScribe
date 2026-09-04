import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()
while tl.GetTrackCount("subtitle"):
    tl.DeleteTrack("subtitle", tl.GetTrackCount("subtitle"))

def show(tag):
    print(f"  [{tag}]", [(i, tl.GetTrackName("subtitle", i),
                          len(tl.GetItemListInTrack("subtitle", i) or []))
                         for i in range(1, tl.GetTrackCount("subtitle") + 1)])

# 1) first track + EN srt
tl.AddTrack("subtitle")
en = mp.ImportMedia([os.path.join(SP, "cal_zero.srt")])[0]
mp.AppendToTimeline([en]); tl.SetTrackName("subtitle", 1, "Subs EN")
show("after EN")

# 2) insert a NEW subtitle track at index 1 -> should push EN to index 2
print("  AddTrack at index 1:", tl.AddTrack("subtitle", {"index": 1}))
show("after insert")

# 3) append AR -> should land on the (empty) track 1
ar = mp.ImportMedia([os.path.join(SP, "cal_ten.srt")])[0]
mp.AppendToTimeline([ar])
show("after AR")
for i in range(1, tl.GetTrackCount("subtitle") + 1):
    for it in (tl.GetItemListInTrack("subtitle", i) or []):
        print(f"    track{i}: {it.GetStart()} {it.GetName()!r}")
