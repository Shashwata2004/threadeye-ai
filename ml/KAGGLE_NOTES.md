# Kaggle: what is known, what we measured, what is still unknown

Checked 2026-10-19. Every line says where it comes from:
**[doc]** Kaggle's own documentation (kaggle.com/docs/notebooks, kaggle.com/docs/efficient-gpu-usage),
**[cli]** the Kaggle CLI source and docs (kaggle 2.2.4, github.com/Kaggle/kaggle-cli/docs),
**[ui]** seen in the Kaggle web UI on this account, **[measured]** our own runs,
**[unknown]** not established — do not plan as if it were true.

## Machines and limits

- [ui] Accelerators offered to this account: **GPU T4 x2** and **TPU v5e-8** only. There is no P100 any
  more ([doc] pages still mention P100 and TPU v3-8; they are out of date).
- [cli] `machine_shape` / `--accelerator` names: `NvidiaTeslaT4` means T4 x2; also listed: `NvidiaL4`,
  `NvidiaL4X1`, `NvidiaTeslaA100`, `NvidiaH100`, `NvidiaRtxPro6000`, `TpuV5E8`, `TpuV6E8`. The CLI sends
  the name unchecked ("the allowed names are in an enum that is not currently included in kagglesdk").
  [measured] `NvidiaTeslaP100` was silently ignored: the run went to T4 x2. The other GPU names are not in
  this account's UI list: assume they are not available.
- [doc] T4 x2 machine: 2 x Tesla T4 (16 GB each), **4 CPU cores**, 29 GB RAM.
- [doc] A session may run **12 hours** (CPU and GPU; 9 h for TPU). "In order to save successfully, the
  entire Notebook must execute within 12 hours": a run that hits the limit does not save a version.
- [doc] Weekly GPU quota: 30 hours "or sometimes higher depending on demand".
  [measured] T4 x2 is charged 1 quota hour per clock hour (3.85 h charged over 3.73 h of one session),
  not 2. [measured] Cancelled sessions were not charged: after cancelling, used quota dropped
  (14.63 h → 12.50 h, then 13.11 h → 1.11 h).
- [doc] "Free GPU availability is limited: in busy times, you might be placed in a queue." No queue
  position or waiting time is shown anywhere. [measured] Waits of 15 min to over 2 hours for T4 x2.
- [ui] At most **2 batch GPU sessions** per account at once, queued ones included ("Maximum batch GPU
  session count of 2 reached").
- [doc] The same notebook can have several batch sessions at once; Kaggle advises cancelling outdated ones.
- [doc] Interactive (editor) sessions: 20 min idle (60 min per the GPU tips page) then they stop. Batch
  runs (Save & Run All, or `kernels push`) do not need the browser.

## Files

- [doc] `/kaggle/working`: up to 20 GB, saved as the version's output. Everything else (`/kaggle/tmp`) is
  scratch and lost when the session ends.
- [doc] A notebook's output can be attached to another notebook as an input ("chaining notebooks").
  [measured] A notebook whose input notebook is still running waits in QUEUED until that input finishes
  (twice: the training waited for the build; train-2 waited for a stuck train run).
- [unknown] Whether the output of a run that ends in ERROR is kept. `kernels files` with a version number
  ignores the version and lists the last successful output, so we could not check. Our scripts therefore
  never end in an error after training starts.

## CLI behaviour

- [cli] `kernels status` values: QUEUED, RUNNING, COMPLETE, ERROR, CANCEL_REQUESTED, CANCEL_ACKNOWLEDGED,
  NEW_SCRIPT. It reports the latest version only.
- [cli] `kernels logs <owner/slug>` returns the latest session's saved log (empty while it runs).
  `kernels logs -f` streams the live log while the session runs (server-sent events) and the saved log
  after it ends. [measured] It works for a running session; it returns nothing while QUEUED, and an HTTP
  500 for a session that had stopped responding.
- [cli] `kernels push --timeout SECONDS` sets the session's maximum run time on Kaggle's side.
- [cli] There is no command to cancel a run: cancel in the UI (Active Events → ⋮ → Stop Session).
- [cli] `kernels output` downloads the latest version's output (`--file-pattern` limits it).

## What went wrong on 2026-10-18/19 and what we do about it

- Version 6 and a debug run stayed RUNNING for hours with no log output; Version 7 (10.5 h training
  budget) never finished and was lost at the 12-hour limit. Cause [unknown]: the runs gave no logs.
- Rules from now on:
  - Train in sessions of about 3.5 h, resuming from the previous session's last epoch
    (`ml/kaggle/train.py`, two notebooks taking turns); checkpoints are written to `/kaggle/working/runs`
    at every epoch.
  - Watch every run with `kernels logs -f` (scratchpad `watch_session.sh`): no log while RUNNING means
    the session is stuck; cancel it instead of waiting.
  - Only one dependent notebook per input; cancel stuck runs at once, they block notebooks that read
    their output.

## Other free GPUs (checked 2026-10-19)

Google Colab, free tier:
- [doc: research.google.com/colaboratory/faq.html] "notebooks can run for at most 12 hours, depending on
  availability and your usage patterns"; limits "can vary over time" and are not published; GPU types
  "vary over time"; idle runtimes time out; VMs are deleted when idle or at the maximum lifetime.
- [doc] Not allowed on the free tier: remote SSH or desktops, and "bypassing the notebook UI". So a run is
  started and watched in the browser; the CLI cannot drive it.
- [doc] Background execution (keeps running with the browser closed) is Colab Pro+ only.
- [reported, not official] T4 GPU, 2 vCPUs, ~12 GB RAM, ~60–100 GB disk; ~90 min idle timeout; GPU often
  refused at busy hours or after heavy use.
- For us: one T4 and 2 vCPUs (Kaggle: two T4s, 4 vCPUs), so slower; checkpoints must go to Google Drive
  to survive a disconnect; the dataset is fetched from Kaggle in every session.

Modal: [doc: modal.com/pricing] Starter plan "$30 / month free credits"; T4 $0.000164/s (~$0.59/h), L4
~$0.80/h, A10 ~$1.10/h; 10 GPUs at once. [reported, not official] the free credits need a payment
method on the account. Fully scriptable from a terminal (`modal run`), live logs.

Lightning AI: [reported, not official] one free Studio with restarts every 4 hours; credit amount and
GPU types could not be confirmed.

Hugging Face: free Spaces are CPU only; ZeroGPU is for short calls (minutes), not training.
