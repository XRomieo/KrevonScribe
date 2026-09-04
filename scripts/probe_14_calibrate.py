import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()

def fresh_track():
    while tl.GetTrackCount("subtitle"):
        tl.DeleteTrack("subtitle", tl.GetTrackCount("subtitle"))
    tl.AddTrack("subtitle")

for tag in ("zero", "ten", "zero"):   # repeat 'zero' to test stability
    fresh_track()
    s, e = tl.GetStartFrame(), tl.GetEndFrame()
    items = mp.ImportMedia([os.path.join(SP, f"cal_{tag}.srt")])
    c = items[0]
    stc = c.GetClipProperty("Start TC")
    mp.AppendToTimeline([c])
    cues = tl.GetItemListInTrack("subtitle", 1) or []
    got = cues[0].GetStart() if cues else None
    print(f"{tag:5s} tlStart={s} tlEnd={e} clipStartTC={stc} -> placed={got} "
          f"offsetFromStart={(got - s) if got else None}")
