import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager(); pm.LoadProject("ZZ_SubtitleToolProbe")
proj = pm.GetCurrentProject(); mp = proj.GetMediaPool(); tl = proj.GetCurrentTimeline()

def probe(name, obj):
    print(f"\n=== {name} ===")
    d = [x for x in dir(obj) if not x.startswith("_")]
    print("dir():", d if d else "(empty)")
    # Fusion remote objects often answer GetAttrs / help
    for meth in ("GetAttrs", "GetHelp"):
        try:
            f = getattr(obj, meth, None)
            if f: print(f"  {meth}:", str(f())[:300])
        except Exception as e:
            print(f"  {meth} EXC:", e)

probe("Timeline", tl)
probe("MediaPool", mp)

# brute-force: does an undocumented subtitle import method exist?
cands = ["ImportSubtitle", "ImportSubtitles", "ImportSubtitleFromFile", "AddSubtitle",
         "AddSubtitles", "CreateSubtitlesFromFile", "ImportCaptions", "ImportCaption",
         "InsertSubtitleIntoTimeline", "ImportSubtitleIntoTimeline"]
print("\n=== brute force method existence ===")
for host, hname in ((tl, "Timeline"), (mp, "MediaPool"), (proj, "Project"), (resolve, "Resolve")):
    for c in cands:
        f = getattr(host, c, None)
        if f is not None:
            print(f"  FOUND {hname}.{c} -> {f}")
print("  (done)")
