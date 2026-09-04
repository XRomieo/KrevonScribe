import sys, os, json
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); proj = pm.GetCurrentProject()
print("project:", proj.GetName())
mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()
print("timeline:", tl.GetName())

print("\n=== timeline settings keys mentioning font/subtitle/caption/text ===")
ts = tl.GetSetting()
hits = {k: v for k, v in ts.items() if any(w in k.lower() for w in ("font", "subtitle", "caption", "text", "style"))}
print(json.dumps(hits, indent=2, ensure_ascii=False))
print("(total timeline settings:", len(ts), ")")

print("\n=== project settings keys mentioning font/subtitle/caption ===")
ps = proj.GetSetting()
hits2 = {k: v for k, v in ps.items() if any(w in k.lower() for w in ("font", "subtitle", "caption", "style"))}
print(json.dumps(hits2, indent=2, ensure_ascii=False))
print("(total project settings:", len(ps), ")")

print("\n=== AddTrack subtitle + append ===")
print("AddTrack:", tl.AddTrack("subtitle"))
print("subtitle track count:", tl.GetTrackCount("subtitle"))
print("SetTrackName:", tl.SetTrackName("subtitle", 1, "Subs EN"))
print("GetTrackName:", tl.GetTrackName("subtitle", 1))

# find the imported subtitle media pool item
root = mp.GetRootFolder()
subs = [c for c in root.GetClipList() if c.GetClipProperty("Type") == "Subtitle"]
print("subtitle clips in pool:", [c.GetName() for c in subs])
if subs:
    res = mp.AppendToTimeline([{"mediaPoolItem": subs[0], "startFrame": 0, "endFrame": 167, "trackIndex": 1}])
    print("AppendToTimeline(dict):", res)
    if not res:
        res = mp.AppendToTimeline([subs[0]])
        print("AppendToTimeline(plain):", res)
    items = tl.GetItemListInTrack("subtitle", 1)
    print("items on subtitle track 1:", len(items) if items else 0)
    for it in (items or [])[:5]:
        print("   ", repr(it.GetName()))
        print("     GetProperty():", it.GetProperty())
