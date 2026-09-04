"""Stage 4: real timeline. Tests audio track enable/disable, audio-only render, subtitle append."""
import sys, os, time
sys.path.insert(0, "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
import DaVinciResolveScript as dvr
SP = sys.argv[1]
resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager()
print("LoadProject:", pm.LoadProject("ZZ_SubtitleToolProbe"))
proj = pm.GetCurrentProject()
mp = proj.GetMediaPool()
print("project:", proj.GetName())

# import the test clip
items = mp.ImportMedia([os.path.join(SP, "probe_clip.mov")])
print("imported clip:", items and items[0].GetName())
clip = items[0]

tl = mp.CreateTimelineFromClips("ProbeTL2", [clip])
print("timeline from clips:", tl.GetName() if tl else None)
tl = proj.GetCurrentTimeline()
print("current timeline:", tl.GetName(), "start", tl.GetStartFrame(), "end", tl.GetEndFrame())

print("\n=== audio tracks ===")
n = tl.GetTrackCount("audio")
for i in range(1, n + 1):
    print(f"  A{i}: name={tl.GetTrackName('audio', i)!r} sub={tl.GetTrackSubType('audio', i)!r} "
          f"enabled={tl.GetIsTrackEnabled('audio', i)} items={len(tl.GetItemListInTrack('audio', i) or [])}")
print("  SetTrackEnable(audio,1,False):", tl.SetTrackEnable("audio", 1, False))
print("  GetIsTrackEnabled ->", tl.GetIsTrackEnabled("audio", 1))
print("  SetTrackEnable(audio,1,True):", tl.SetTrackEnable("audio", 1, True))

print("\n=== audio-only render probe ===")
print("LoadRenderPreset('Audio Only'):", proj.LoadRenderPreset("Audio Only"))
cur = proj.GetCurrentRenderFormatAndCodec()
print("current format/codec after preset:", cur)
print("SetCurrentRenderFormatAndCodec('wav','lpcm'):", proj.SetCurrentRenderFormatAndCodec("wav", "lpcm"))
print("now:", proj.GetCurrentRenderFormatAndCodec())
outdir = os.path.join(SP, "renderout"); os.makedirs(outdir, exist_ok=True)
ok = proj.SetRenderSettings({
    "TargetDir": outdir,
    "CustomName": "probe_audio",
    "ExportVideo": False,
    "ExportAudio": True,
    "AudioCodec": "lpcm",
    "AudioBitDepth": 16,
    "AudioSampleRate": 48000,
})
print("SetRenderSettings:", ok)
job = proj.AddRenderJob()
print("AddRenderJob:", job)
print("StartRendering:", proj.StartRendering([job], isInteractiveMode=False))
for _ in range(60):
    if not proj.IsRenderingInProgress():
        break
    time.sleep(1)
print("job status:", proj.GetRenderJobStatus(job))
print("files in outdir:", os.listdir(outdir))
proj.DeleteAllRenderJobs()

print("\n=== subtitle append on a real timeline ===")
print("AddTrack subtitle:", tl.AddTrack("subtitle"))
print("subtitle count:", tl.GetTrackCount("subtitle"))
print("SetTrackName:", tl.SetTrackName("subtitle", 1, "Subs EN"))
root = mp.GetRootFolder()
subs = [c for c in root.GetClipList() if c.GetClipProperty("Type") == "Subtitle"]
print("subtitle pool clips:", [c.GetName() for c in subs])
if subs:
    r = mp.AppendToTimeline([{"mediaPoolItem": subs[0], "trackIndex": 1, "mediaType": 1}])
    print("append w/ trackIndex+mediaType:", r)
    items_t = tl.GetItemListInTrack("subtitle", 1)
    print("items on subtitle track:", len(items_t or []))
    for it in (items_t or [])[:4]:
        print("    ", repr(it.GetName()), it.GetStart(), it.GetEnd())
