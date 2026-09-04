import sys, json
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()
c = [x for x in mp.GetRootFolder().GetClipList() if x.GetClipProperty("Type") == "Subtitle"][0]
props = c.GetClipProperty()
interesting = {k: v for k, v in props.items() if v not in ("", None)}
print(json.dumps(interesting, indent=1, ensure_ascii=False))
print("\ntimeline start:", tl.GetStartFrame(), "tc:", tl.GetStartTimecode())
print("timeline fps setting:", tl.GetSetting("timelineFrameRate"))
