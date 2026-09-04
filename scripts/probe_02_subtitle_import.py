"""Stage 2: can Resolve import SRT / styled ASS into a subtitle track?
Creates a throwaway project named ZZ_SubtitleToolProbe. Non-destructive to existing projects."""
import sys, os
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr

SP = sys.argv[1]
PROBE = "ZZ_SubtitleToolProbe"

resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager()

existing = pm.GetProjectListInCurrentFolder()
print("projects before:", existing)
if PROBE in existing:
    pm.LoadProject(PROBE)
else:
    print("CreateProject ->", bool(pm.CreateProject(PROBE)))
proj = pm.GetCurrentProject()
print("current project:", proj.GetName())

mp = proj.GetMediaPool()

# --- render format/codec discovery for audio-only export ---
print("\n=== render formats ===")
fmts = proj.GetRenderFormats()
print(fmts)
for f in ("wav", "mp3", "aiff"):
    if f in (fmts or {}).values() or f in (fmts or {}):
        pass
print("codecs for 'wav':", proj.GetRenderCodecs("wav"))
print("render presets:", proj.GetRenderPresetList())

# --- timeline ---
tl = proj.GetCurrentTimeline()
if tl is None:
    tl = mp.CreateEmptyTimeline("ProbeTL")
    print("\ncreated empty timeline:", tl.GetName() if tl else None)
print("timeline:", tl.GetName(), "start", tl.GetStartFrame(), "end", tl.GetEndFrame())
for tt in ("video", "audio", "subtitle"):
    print(f"  {tt} tracks:", tl.GetTrackCount(tt))

# --- import subtitle files ---
for name in ("sample.srt", "sample.ass"):
    path = os.path.join(SP, name)
    print(f"\n=== ImportMedia {name} ===")
    items = mp.ImportMedia([path])
    print("  returned:", items)
    if items:
        for it in items:
            print("   name:", it.GetName())
            print("   clip type:", it.GetClipProperty("Type"))
            print("   duration:", it.GetClipProperty("Duration"))
