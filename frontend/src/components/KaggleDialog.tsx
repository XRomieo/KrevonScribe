import { useState } from "react"
import { KeyRound, Loader2 } from "lucide-react"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Field } from "./Section"
import { api } from "@/lib/api"
import type { KaggleStatus, Settings } from "@/lib/types"

export function KaggleDialog({
  open, onOpenChange, onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSaved: (k: KaggleStatus, s: Settings) => void
}) {
  const [token, setToken] = useState("")
  const [username, setUsername] = useState("")
  const [key, setKey] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  async function save() {
    setBusy(true); setError("")
    const res = await api.save_kaggle_credentials({ token, username, key })
    setBusy(false)
    if (!res.ok) { setError(res.error); return }
    setToken(""); setKey("")
    onSaved(res.kaggle, res.settings)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-line bg-panel sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[15px]">
            <KeyRound className="size-4 text-en" /> Kaggle credentials
          </DialogTitle>
          <DialogDescription className="text-[12px] leading-relaxed text-ink-dim">
            Create a token at kaggle.com/settings under API. Credentials are written to
            your <span className="font-mono text-ink-dim">~/.kaggle</span> folder and never
            leave this machine except to Kaggle itself.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          <Field label="API token" htmlFor="k-token">
            <Input
              id="k-token" type="password" value={token} placeholder="paste token"
              onChange={(e) => setToken(e.target.value)}
              className="font-mono text-[12px]"
            />
          </Field>

          <div className="flex items-center gap-3">
            <span className="h-px flex-1 bg-line" />
            <span className="label-etched">or legacy key pair</span>
            <span className="h-px flex-1 bg-line" />
          </div>

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

          <p className="text-[11px] leading-relaxed text-ink-faint">
            Your username is also used to name the private dataset and kernel this tool
            creates, so fill it in either way.
          </p>

          {error && <p className="text-[12px] text-alert">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={busy || (!token && !(username && key))}>
            {busy && <Loader2 className="size-3.5 animate-spin" />} Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
