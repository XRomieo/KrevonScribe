import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool()
tls = {proj.GetTimelineByIndex(i).GetName(): proj.GetTimelineByIndex(i)
       for i in range(1, proj.GetTimelineCount() + 1)}
main = tls["ProbeTL2"]; other = next(t for n, t in tls.items() if n != "ProbeTL2")
proj.SetCurrentTimeline(main); tl = proj.GetCurrentTimeline()
while tl.GetTrackCount("subtitle"):
    tl.DeleteTrack("subtitle", tl.GetTrackCount("subtitle"))
def show(tag):
    print(f"  [{tag}]", [(i, len(tl.GetItemListInTrack("subtitle", i) or []))
                         for i in range(1, tl.GetTrackCount("subtitle") + 1)])

tl.AddTrack("subtitle")
ar = mp.ImportMedia([os.path.join(SP, "cal_ten.srt")])[0]
mp.AppendToTimeline([ar]); show("AR on t1")
print("  insert track at index 1:", tl.AddTrack("subtitle", {"index": 1})); show("inserted")

# force Resolve to drop its cached "current subtitle track"
proj.SetCurrentTimeline(other)
proj.SetCurrentTimeline(main)
tl = proj.GetCurrentTimeline()
print("  bounced timelines; subtitle tracks:", tl.GetTrackCount("subtitle"))

en = mp.ImportMedia([os.path.join(SP, "cal_zero.srt")])[0]
mp.AppendToTimeline([en]); show("EN appended")
for i in range(1, tl.GetTrackCount("subtitle") + 1):
    for it in (tl.GetItemListInTrack("subtitle", i) or []):
        print(f"    track{i}: frame={it.GetStart()} {it.GetName()!r}")
