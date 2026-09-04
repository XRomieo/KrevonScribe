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
    print(f"  [{tag}]", [(i, len(tl.GetItemListInTrack("subtitle", i) or []),
                          "locked" if tl.GetIsTrackLocked("subtitle", i) else "open")
                         for i in range(1, tl.GetTrackCount("subtitle") + 1)])
tl.AddTrack("subtitle")
ar = mp.ImportMedia([os.path.join(SP, "cal_ten.srt")])[0]
mp.AppendToTimeline([ar]); tl.SetTrackName("subtitle", 1, "Subs AR"); show("AR on t1")
tl.AddTrack("subtitle"); tl.SetTrackName("subtitle", 2, "Subs EN")
print("  lock track 1:", tl.SetTrackLock("subtitle", 1, True)); show("locked t1")
en = mp.ImportMedia([os.path.join(SP, "cal_zero.srt")])[0]
mp.AppendToTimeline([en]); show("EN appended")
tl.SetTrackLock("subtitle", 1, False)
for i in range(1, tl.GetTrackCount("subtitle") + 1):
    for it in (tl.GetItemListInTrack("subtitle", i) or []):
        print(f"    track{i} ({tl.GetTrackName('subtitle',i)}): frame={it.GetStart()} {it.GetName()!r}")
