# Running the demo on a laptop

The competition demo runs the app on a laptop against the shared Supabase database, with ThreadEye's
trained detector (YOLOX-S, ONNX Runtime on the CPU) instead of the simulated one. The camera video is
still the simulator's sample roll; the top banner says so.

Measured on an HP 15 (Core i5-1335U, 8 GB, Ubuntu): 1.2 s per sampled frame; the 58 s sample roll is
processed in about 28 s, so the boxes keep ahead of the video.

## Once per laptop (Ubuntu)

1. Get the code: `git clone https://github.com/Shashwata2004/threadeye-ai.git` (private: ask for access).
2. Put `.env.cloud` in the repository folder. Shashwata sends it privately; it holds the database
   password, so never commit it or post it in a chat group.
3. Install the tools:
   - uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then open a new terminal
   - Node.js 20 or newer and pnpm: `sudo apt install nodejs npm && sudo npm i -g pnpm`

## Every time

```bash
./scripts/run_demo.sh
```

Open http://localhost:3000 and sign in with a demo account (password: `THREADEYE_DEMO_PASSWORD` in
`.env.cloud`). The first run installs the Python and Node packages and downloads the sample roll's video
and the trained model (about 55 MB) from Supabase; later runs start in seconds and work with what is
already downloaded.

## Before the demo

- Plug in the charger and set Settings → Power → Power Mode to Performance: the model runs on the CPU.
- Close other heavy programs (a second browser, video calls): the laptop needs about 2 GB of free memory.
- Do one full inspection beforehand to check that boxes appear on the live screen.

## Updating the model

On the training laptop, after a Kaggle run: `make cloud-upload-model MODEL=path/to/model` (the folder
with `threadeye_s.onnx`, `model_info.json`, `test_report.json`). Demo laptops get it on their next
`./scripts/run_demo.sh`.
