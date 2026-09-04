# Kaggle setup (one time, ~5 minutes)

The tool does no transcription locally. It uploads your timeline audio to Kaggle
as a private dataset, runs a GPU notebook there with faster-whisper, and pulls
back `segments.json`. That needs a Kaggle account with two things switched on.

## 1. Account

Sign in or sign up at <https://www.kaggle.com>. A free account is enough.

## 2. Phone verification — do not skip this

Go to <https://www.kaggle.com/settings> → **Phone Verification** → verify with an
SMS code.

This is the step people miss. An unverified Kaggle account **cannot use a GPU and
cannot enable internet access inside a notebook**. Our kernel needs both:

- **GPU** — CPU transcription of a 30-minute timeline takes over an hour.
- **Internet** — the kernel runs `pip install faster-whisper` and downloads the
  Whisper model weights at runtime.

Without verification the job fails, or silently falls back to a slow CPU run.

## 3. Credentials — pick one

### Option A: OAuth (easiest, recommended)

The kaggle 2.2.4 client we ship can log in through the browser. Nothing to
download, nothing to paste:

```bash
.venv/bin/kaggle auth login
```

Approve in the browser and the credentials are cached locally. That is the
whole step.

### Option B: API token

Go to <https://www.kaggle.com/settings> -> **API** -> **Create New Token**.
Your browser downloads `kaggle.json`:

```json
{"username":"yourname","key":"0123456789abcdef0123456789abcdef"}
```

Treat that key like a password.

Install it from the app's **Settings** tab (it writes the file with `0600`
permissions), or by hand:

```bash
mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/kaggle.json && chmod 600 ~/.kaggle/kaggle.json
```

On Windows, put it at `C:\Users\<you>\.kaggle\kaggle.json`.

## 4. Accept the notebook terms

Open <https://www.kaggle.com/code> and click **New Notebook** once, then close
it. The very first notebook a new account creates triggers a one-time terms
prompt; getting it out of the way in the browser stops the API run from
stalling on it.

## 5. Check it

```bash
.venv/bin/python -m resolve_subtitle_tool.check_kaggle
```

That checks credentials, authentication and API reachability in a second or
two. To actually *prove* GPU and internet are granted, add `--full` — it pushes
a throwaway kernel that reports the hardware it was handed and whether it can
reach the network:

```bash
.venv/bin/python -m resolve_subtitle_tool.check_kaggle --full
```

That spends about a minute of your weekly quota, and it is the only way to be
sure: Kaggle exposes no API field for phone-verification status.

## Quotas worth knowing

| Limit | Free tier |
|---|---|
| GPU hours | 30 per week |
| Notebook run time | 12 h max per session |
| Dataset size | 200 GB total, plenty for audio |
| Concurrent GPU sessions | 1 |

A 30-minute timeline on `small` takes roughly 2–3 GPU-minutes, so the weekly
quota is not a practical constraint.

## Where things land in your Kaggle account

- A private dataset per job, named `resolve-audio-<slug>`.
- A private kernel (script) per job, named `resolve-transcribe-<slug>`.

Both are private and safe to delete afterwards from your Kaggle account pages.
