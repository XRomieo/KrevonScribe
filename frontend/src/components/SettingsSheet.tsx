import { useState } from "react"
import { ExternalLink, FolderOpen, Loader2 } from "lucide-react"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { api } from "@/lib/api"
import type { KaggleStatus, Settings } from "@/lib/types"
import { cn } from "@/lib/utils"

const KAGGLE_SETTINGS_URL = "https://www.kaggle.com/settings"

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-edge pt-4 first:border-0 first:pt-0">
      <h3 className="eyebrow mb-3">{title}</h3>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function Field({
  label, hint, htmlFor, children,
}: { label: string; hint?: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-[12.5px] font-medium text-ink-2">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11.5px] leading-relaxed text-ink-3">{hint}</p>}
    </div>
  )
}

function SwitchRow({
  label, hint, checked, onChange,
}: { label: string; hint: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <Switch checked={checked} onCheckedChange={onChange} className="mt-0.5 shrink-0" />
      <span className="min-w-0">
        <span className="block text-[12.5px] font-medium text-ink-2">{label}</span>
        <span className="mt-0.5 block text-[11.5px] leading-relaxed text-ink-3">{hint}</span>
      </span>
    </label>
  )
}

function PathField({
  label, hint, value, onBrowse,
}: { label: string; hint?: string; value: string; onBrowse: () => void }) {
  return (
    <Field label={label} hint={hint}>
      <div className="flex items-stretch gap-1.5">
        <span
          title={value}
          className="min-w-0 flex-1 truncate rounded-md border border-edge bg-sink px-2.5 py-2 font-mono text-[11px] leading-tight text-ink-2"
        >
          {value || "—"}
        </span>
        <button
          type="button"
          onClick={onBrowse}
          title={`Choose ${label.toLowerCase()}`}
          className="flex shrink-0 items-center rounded-md border border-edge px-2.5 text-ink-3 transition-colors hover:border-edge-lit hover:text-ink"
        >
          <FolderOpen className="size-3.5" />
        </button>
      </div>
    </Field>
  )
}

export function SettingsSheet({
  open, onOpenChange, settings, kaggle, onPatch, onKaggleSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  settings: Settings
  kaggle: KaggleStatus | null
  onPatch: (v: Partial<Settings>) => void
  onKaggleSaved: (k: KaggleStatus, s: Settings) => void
}) {
  const [token, setToken] = useState("")
  const [username, setUsername] = useState("")
  const [key, setKey] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [showKeyPair, setShowKeyPair] = useState(false)

  async function saveCredentials() {
    setBusy(true); setError("")
    const res = await api.save_kaggle_credentials({ token, username, key })
    setBusy(false)
    if (!res.ok) { setError(res.error); return }
    setToken(""); setKey("")
    onKaggleSaved(res.kaggle, res.settings)
  }

  async function browse(which: "srt_dir") {
    const res = await api.choose_folder(settings[which])
    if (res.ok && res.path) onPatch({ [which]: res.path } as Partial<Settings>)
  }

  const configured = !!kaggle?.configured
  const canSave = !!token || !!(username && key)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-y-auto border-edge bg-shell sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-[17px]">Settings</DialogTitle>
          <DialogDescription className="text-[12.5px] leading-relaxed text-ink-3">
            Everything here is saved as you change it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          <Group title="Kaggle account">
            <div
              className={cn(
                "flex items-center gap-2.5 rounded-lg border px-3 py-2.5",
                configured ? "border-go/25 bg-go/[0.06]" : "border-edge bg-sink",
              )}
            >
              <span className={cn("size-1.5 shrink-0 rounded-full", configured ? "bg-go" : "bg-ink-3")} />
              <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-2">
                {configured
                  ? `Signed in as ${kaggle?.username || settings.kaggle_username || "your account"}`
                  : "No credentials yet"}
              </span>
              <button
                type="button"
                onClick={() => void api.open_external(KAGGLE_SETTINGS_URL)}
                className="flex shrink-0 items-center gap-1 text-[11.5px] text-ink-3 transition-colors hover:text-ink"
              >
                Get a token <ExternalLink className="size-3" />
              </button>
            </div>

            <Field
              label="API token"
              hint="From kaggle.com → Settings → API. Written to your ~/.kaggle folder; it only ever goes to Kaggle."
              htmlFor="k-token"
            >
              <Input
                id="k-token" type="password" value={token} placeholder="Paste the token" autoFocus
                onChange={(e) => setToken(e.target.value)}
                className="font-mono text-[12px]"
              />
            </Field>

            {showKeyPair ? (
              <div className="grid grid-cols-2 gap-3">
                <Field label="Username" htmlFor="k-user">
                  <Input
                    id="k-user" value={username} onChange={(e) => setUsername(e.target.value)}
                    className="font-mono text-[12px]"
                  />
                </Field>
                <Field label="Key" htmlFor="k-key">
                  <Input
                    id="k-key" type="password" value={key} onChange={(e) => setKey(e.target.value)}
                    className="font-mono text-[12px]"
                  />
                </Field>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowKeyPair(true)}
                className="text-[11.5px] text-ink-3 underline-offset-2 transition-colors hover:text-ink-2 hover:underline"
              >
                Use a username and key instead
              </button>
            )}

            {error && <p className="text-[12px] text-stop">{error}</p>}

            <button
              type="button"
              onClick={saveCredentials}
              disabled={busy || !canSave}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3.5 py-2 text-[12.5px] font-semibold transition-[filter,opacity]",
                canSave && !busy
                  ? "bg-pulse text-[#26060f] hover:brightness-110"
                  : "cursor-not-allowed border border-edge text-ink-3",
              )}
            >
              {busy && <Loader2 className="size-3.5 animate-spin" />}
              Save credentials
            </button>

            {configured && !settings.kaggle_username && (
              <Field
                label="Kaggle username"
                hint="Used to name the private dataset and kernel this tool creates."
              >
                <Input
                  value={settings.kaggle_username}
                  onChange={(e) => onPatch({ kaggle_username: e.target.value })}
                  className="font-mono text-[12px]"
                />
              </Field>
            )}
          </Group>

          <Group title="Subtitles">
            <SwitchRow
              label="Re-time cues against the audio"
              hint="Whisper infers its timestamps and they drift. Forced alignment measures them instead, and costs about a minute of GPU time."
              checked={settings.forced_alignment}
              onChange={(v) => onPatch({ forced_alignment: v })}
            />

            <PathField
              label="Where subtitle files are written" value={settings.srt_dir}
              onBrowse={() => void browse("srt_dir")}
            />
          </Group>

          <Group title="Transcription model">
            <Field
              label="Code-switch checkpoint"
              hint="Transcribes Arabic and English in one pass, each word in the script it was spoken in. Scored 94.7% against hand-marked language spans; the alternative, IbrahimAmin/code-switched-egyptian-arabic-whisper-small, scored 93.5%."
            >
              <Input
                value={settings.code_switch_model}
                onChange={(e) => onPatch({ code_switch_model: e.target.value })}
                className="font-mono text-[11.5px]"
              />
            </Field>

            <SwitchRow
              label="Never mix scripts in one cue"
              hint="The speaker switches language mid-sentence. Splitting keeps each cue in one script, which one font can typeset; turning this off keeps such sentences whole."
              checked={settings.cue_script_policy === "split"}
              onChange={(v) => onPatch({ cue_script_policy: v ? "split" : "mixed" })}
            />
          </Group>
        </div>
      </DialogContent>
    </Dialog>
  )
}
