"""Stage 5: alternative routes to get SRT cues onto a timeline."""
import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool()
tl = proj.GetCurrentTimeline()
print("timeline:", tl.GetName(), "subtitle tracks:", tl.GetTrackCount("subtitle"))

srt = os.path.join(SP, "sample.srt")

print("\n=== route A: timeline.ImportIntoTimeline(srt) ===")
try:
    print("  ->", tl.ImportIntoTimeline(srt))
except Exception as e:
    print("  EXC:", e)
print("  items on subtitle track 1:", len(tl.GetItemListInTrack("subtitle", 1) or []))

print("\n=== route B: mediaPool.ImportTimelineFromFile(srt) ===")
try:
    print("  ->", mp.ImportTimelineFromFile(srt))
except Exception as e:
    print("  EXC:", e)

print("\n=== route C: export DRT to inspect schema ===")
drt = os.path.join(SP, "probe_timeline.drt")
print("  Export DRT:", tl.Export(drt, resolve.EXPORT_DRT, resolve.EXPORT_NONE))
print("  exists:", os.path.exists(drt), os.path.getsize(drt) if os.path.exists(drt) else 0)
fcp = os.path.join(SP, "probe_timeline.fcpxml")
print("  Export FCPXML 1.10:", tl.Export(fcp, resolve.EXPORT_FCPXML_1_10, resolve.EXPORT_NONE))
print("  exists:", os.path.exists(fcp), os.path.getsize(fcp) if os.path.exists(fcp) else 0)
otio = os.path.join(SP, "probe_timeline.otio")
print("  Export OTIO:", tl.Export(otio, resolve.EXPORT_OTIO, resolve.EXPORT_NONE))
print("  exists:", os.path.exists(otio), os.path.getsize(otio) if os.path.exists(otio) else 0)
