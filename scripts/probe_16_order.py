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
    print(f"  [{tag}]", [(i, len(tl.GetItemListInTrack("subtitle", i) or []))
                         for i in range(1, tl.GetTrackCount("subtitle") + 1)])
tl.AddTrack("subtitle")
en = mp.ImportMedia([os.path.join(SP, "cal_zero.srt")])[0]
mp.AppendToTimeline([en]); show("EN on t1")
print("  AddTrack (end):", tl.AddTrack("subtitle")); show("added t2")
ar = mp.ImportMedia([os.path.join(SP, "cal_ten.srt")])[0]
mp.AppendToTimeline([ar]); show("AR appended")
for i in range(1, tl.GetTrackCount("subtitle") + 1):
    for it in (tl.GetItemListInTrack("subtitle", i) or []):
        print(f"    track{i}: frame={it.GetStart()} {it.GetName()!r}")
