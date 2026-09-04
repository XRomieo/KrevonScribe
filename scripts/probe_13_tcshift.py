import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()
# clean subtitle tracks
while tl.GetTrackCount("subtitle"):
    tl.DeleteTrack("subtitle", tl.GetTrackCount("subtitle"))
tl.AddTrack("subtitle"); tl.SetTrackName("subtitle", 1, "Subs EN")
start, end = tl.GetStartFrame(), tl.GetEndFrame()
print("timeline start:", start, "end:", end, "startTC:", tl.GetStartTimecode())

items = mp.ImportMedia([os.path.join(SP, "sample_tc.srt")])
c = items[0]
print("imported:", c.GetName(), "StartTC:", c.GetClipProperty("Start TC"), "Dur:", c.GetClipProperty("Duration"))
r = mp.AppendToTimeline([c])
print("append ->", bool(r))
cues = tl.GetItemListInTrack("subtitle", 1) or []
print(f"cues on track 1: {len(cues)}")
for it in cues:
    print(f"   start={it.GetStart()} (offset from tl start: {it.GetStart()-start}) text={it.GetName()!r}")
print("\nexpected if absolute-TC honoured: first cue at", start + 12)
