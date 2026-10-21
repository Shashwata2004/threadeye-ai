"""Kaggle step 3 (GPU): train a YOLOX detector on threadeye_v1, evaluate on test, export ONNX.

Inputs: the build notebook's output (threadeye_v1/) and the private dataset "threadeye-ml-code" (params.json
"train" block: model size, epochs, batch). YOLOX (Apache-2.0) is cloned at a pinned commit and run from
source; training starts from its COCO weights.

Rare classes are shown more often with repeat-factor sampling (LVIS): an image whose rarest class appears
in a fraction f of train images is repeated max(1, sqrt(t / f)) times, t = 0.1.
"""

import hashlib
import json
import math
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from pathlib import Path

print("train.py started", flush=True)


def find_inputs(name: str, max_depth: int) -> list[Path]:
    """Matches of ``name`` (may hold a "/") at most ``max_depth`` folders below /kaggle/input, shallowest first.
    Never rglob there: a walk through the attached dataset's 65,000 tiles took over four minutes (2026-10-21,
    inputs mounted as /kaggle/input/{datasets,notebooks}/<owner>/<slug>/), before the first log line."""
    return [p for d in range(max_depth + 1) for p in sorted(Path("/kaggle/input").glob("*/" * d + name))]


PARAMS = json.loads(find_inputs("params.json", 3)[0].read_text()).get("train", {})
SIZE = PARAMS.get("model", "s")  # nano | tiny | s | m
EPOCHS = int(PARAMS.get("epochs", 30))
BATCH = int(PARAMS.get("batch", 16))
MAX_TRAIN = PARAMS.get("max_train_images")  # a smoke test sets a small number
TRAIN_BUDGET_H = float(PARAMS.get("train_budget_h", 10.0))
EVAL_INTERVAL = int(PARAMS.get("eval_interval", 0))  # 0: no evaluation during training
RESUME = PARAMS.get("resume", "auto")
INIT_FROM_PREVIOUS = bool(PARAMS.get("init_from_previous", False))
"""Fine-tune: start a new schedule from the newest attached checkpoint's weights (e.g. after a data fix),
instead of YOLOX's COCO weights. Not a resume: optimizer, epoch count and learning-rate schedule start over."""
LR_SCALE = float(PARAMS.get("lr_scale", 1.0))
EVAL_ONLY = bool(PARAMS.get("eval_only", False))
"""Train nothing: test the newest attached checkpoint on this notebook's dataset (the previous model on a
patched test set, as the baseline a new model is compared with)."""
"""Continue from the last epoch of a previous session attached as an input (the other training notebook:
threadeye-train and threadeye-train-2 take turns). "auto": resume whenever such a checkpoint is attached."""
YOLOX_COMMIT = PARAMS.get("yolox_commit", "main")
DEPTH_WIDTH = {"nano": (0.33, 0.25), "tiny": (0.33, 0.375), "s": (0.33, 0.50), "m": (0.67, 0.75)}
WEIGHTS = {
    "nano": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.pth",
    "tiny": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.pth",
    "s": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_s.pth",
    "m": "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_m.pth",
}

PACKED = next((p.parent for p in find_inputs("threadeye_packed/PACKED", 3)), None)
"""The dataset packed into one tar per split (pack.py): attaching it is quick, the 65,000 loose tiles of a
full build stalled the start of training (2026-10-21). Unpacked onto the local disk before training."""
DATA = PACKED or find_inputs("threadeye_v1/summary.json", 3)[0].parent
PATCH = None if PACKED else next((p.parent for p in find_inputs("threadeye_patch/PATCH", 3)), None)
"""A patch build (build_dataset.py --patch) attached next to the full build: its annotations describe the whole
dataset; its images replace the full build's tiles of the patched sources."""
ANN = PATCH or DATA
TMP = Path("/kaggle/tmp")
YOLOX = TMP / "YOLOX"
WORK = TMP / "data"
OUT = Path("/kaggle/working/model")
RUNS = Path("/kaggle/working/runs")
"""YOLOX writes its checkpoints here, in the notebook's saved output, at every epoch: whatever happens later
in the session (a hang, Kaggle's 12-hour limit), the epochs trained so far are kept and can be resumed."""
T0 = time.time()


sys.path.insert(0, str(find_inputs("kaggle/steplog.py", 4)[0].parent))
import steplog  # time-stamped log with a heartbeat; every step has a time limit


def sh(cmd: str, cwd: Path | None = None, name: str | None = None, limit_min: float = 60) -> None:
    # bash with pipefail: a failing step piped into tee must still fail the notebook.
    steplog.step(name or cmd.split()[0], cmd, limit_min, cwd)


def repeat_factor_sampling(coco: dict, t: float = 0.1) -> dict:
    imgs = coco["images"]
    cats_of: dict[int, set[int]] = {}
    for a in coco["annotations"]:
        cats_of.setdefault(a["image_id"], set()).add(a["category_id"])
    n = len(imgs)
    freq = Counter(c for cs in cats_of.values() for c in cs)
    anns_of: dict[int, list[dict]] = {}
    for a in coco["annotations"]:
        anns_of.setdefault(a["image_id"], []).append(a)
    out_imgs, out_anns, next_img, next_ann = [], [], 1, 1
    repeats = Counter()
    for im in imgs:
        cs = cats_of.get(im["id"], set())
        r = max([1.0] + [math.sqrt(t / (freq[c] / n)) for c in cs])
        u = int(hashlib.sha1(im["file_name"].encode()).hexdigest()[:6], 16) / 0xFFFFFF  # fixed per file
        k = int(r) + (1 if u < r - int(r) else 0)
        repeats[k] += 1
        for _ in range(max(k, 1)):
            out_imgs.append({**im, "id": next_img})
            for a in anns_of.get(im["id"], []):
                out_anns.append({**a, "id": next_ann, "image_id": next_img})
                next_ann += 1
            next_img += 1
    print("repeat factors:", dict(sorted(repeats.items())), "train images", n, "->", len(out_imgs))
    return {**coco, "images": out_imgs, "annotations": out_anns}


# ------------------------------------------------------------------------------------------- setup
sh(f"git clone -q https://github.com/Megvii-BaseDetection/YOLOX.git {YOLOX}")
sh(f"git checkout -q {YOLOX_COMMIT}", cwd=YOLOX)
commit = subprocess.run("git rev-parse HEAD", shell=True, cwd=YOLOX, capture_output=True, text=True).stdout.strip()
print("YOLOX commit", commit)
sh(f"{sys.executable} -m pip -q install loguru tabulate pycocotools thop ninja onnx onnxruntime")
weights = TMP / f"yolox_{SIZE}.pth"
sh(f"curl -sSL -o {weights} {WEIGHTS[SIZE]}")

(WORK / "annotations").mkdir(parents=True, exist_ok=True)
for split in ("train", "val", "test"):
    if (WORK / split).exists():
        continue
    if PACKED is not None:
        (WORK / split).mkdir(parents=True)
        sh(f"tar -xf {PACKED / f'{split}.tar'} -C {WORK / split}", name=f"unpack {split}", limit_min=30)
        continue
    if PATCH is None:
        (WORK / split).symlink_to(DATA / split / "images")
        continue
    # One link per tile: the patch's own images, the full build's for every other tile.
    (WORK / split).mkdir(parents=True)
    own = {f.name for f in (PATCH / split / "images").iterdir()} if (PATCH / split / "images").exists() else set()
    for im in json.loads((PATCH / split / "annotations.json").read_text())["images"]:
        n = im["file_name"]
        (WORK / split / n).symlink_to((PATCH if n in own else DATA) / split / "images" / n)
    print(f"{split}: {len(own)} patch tiles linked over the full build", flush=True)
train = json.loads((ANN / "train/annotations.json").read_text())
if MAX_TRAIN:
    # A fixed random sample: the tiles are ordered by source, and the first N would be one or two sources only
    # (the first smoke test trained on AITEX and stain photos and was tested on everything).
    sample = sorted(train["images"], key=lambda im: hashlib.sha1(im["file_name"].encode()).hexdigest())
    keep = {im["id"] for im in sample[: int(MAX_TRAIN)]}
    train = {**train, "images": [im for im in train["images"] if im["id"] in keep],
             "annotations": [a for a in train["annotations"] if a["image_id"] in keep]}
(WORK / "annotations/train.json").write_text(json.dumps(repeat_factor_sampling(train)))
for split in ("val", "test"):
    shutil.copy(ANN / split / "annotations.json", WORK / f"annotations/{split}.json")
num_classes = len(train["categories"])
class_names = [c["name"] for c in sorted(train["categories"], key=lambda c: c["id"])]

depth, width = DEPTH_WIDTH[SIZE]
exp = TMP / "threadeye_exp.py"
exp.write_text(f'''
import os
from yolox.exp import Exp as MyExp


class Exp(MyExp):
    def __init__(self):
        super().__init__()
        self.depth, self.width = {depth}, {width}
        self.num_classes = {num_classes}
        self.data_dir = "{WORK}"
        self.train_ann, self.val_ann, self.test_ann = "train.json", "val.json", "test.json"
        self.input_size = self.test_size = (640, 640)
        self.max_epoch = {EPOCHS}
        self.no_aug_epochs = max(1, {EPOCHS} // 10)
        self.warmup_epochs = min(5, max(1, {EPOCHS} // 10))
        self.basic_lr_per_img *= {LR_SCALE}
        # No evaluation inside training: two-GPU sessions hung at the barrier right after an in-training
        # evaluation. Each session evaluates once at its end instead (val operating point + test).
        self.data_num_workers = 4
        self.exp_name = "threadeye_{SIZE}"
        self.output_dir = "{RUNS}"
        # Fabric: flips and 90° turns are natural (defects have no up/down); colour jitter for dyed fabric.
        self.flip_prob = 0.5
        self.degrees = 5.0
        # YOLOX's default mosaic scale (0.1, 2) shrinks a tile up to 10x: a 20-px knot or a 3-px broken yarn
        # disappears (the 6-epoch smoke test learned almost nothing). Keep defects near their real pixel size.
        self.mosaic_prob = 0.5
        self.mosaic_scale = (0.5, 1.5)
        # Mixup lays one fabric over another: the blended weave looks like a defect itself.
        self.mixup_prob = 0.0
        self.enable_mixup = False

    # YOLOX's trainer sets exp.eval_interval = 1 when the last no-augmentation epochs begin; that switched the
    # evaluation back on and a session hung after it. The interval is fixed here and the trainer's write ignored.
    @property
    def eval_interval(self):
        return {EVAL_INTERVAL or 10 ** 6}

    @eval_interval.setter
    def eval_interval(self, value):
        pass

    def get_dataset(self, cache=False, cache_type="ram"):
        from yolox.data import COCODataset, TrainTransform
        return COCODataset(data_dir=self.data_dir, json_file=self.train_ann, name="train",
                           img_size=self.input_size,
                           preproc=TrainTransform(max_labels=100, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob))

    def get_eval_dataset(self, **kwargs):
        # YOLOX's --test mode writes a submission file without scoring it; THREADEYE_EVAL_SPLIT=test scores
        # the test split through the normal evaluation instead.
        from yolox.data import COCODataset, ValTransform
        split = os.environ.get("THREADEYE_EVAL_SPLIT", "val")
        return COCODataset(data_dir=self.data_dir, json_file=f"{{split}}.json", name=split, img_size=self.test_size,
                           preproc=ValTransform(legacy=kwargs.get("legacy", False)))
''')

# ------------------------------------------------------------------------------------------- train
# PyTorch >= 2.6 loads checkpoints with weights_only=True, which rejects the numpy scalar YOLOX stores in
# its own checkpoints. These files come from this training run (and YOLOX's official weights), so the
# full loader is acceptable here.
env = f"TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 PYTHONPATH={YOLOX}:$PYTHONPATH"
# Kaggle stops a GPU session at 12 h and keeps nothing it had not written: training gets a time budget, after
# which the newest checkpoint is tested and exported as usual.
run_dir = RUNS / f"threadeye_{SIZE}"
best = run_dir / "best_ckpt.pth"
run_dir.mkdir(parents=True, exist_ok=True)
start = f"-c {weights}"


def db_url() -> str | None:
    """The ThreadEye database (Supabase): the Kaggle secret THREADEYE_DATABASE_URL, or, because Kaggle's secret
    service does not answer runs pushed with the CLI, the file threadeye_db_url.txt in the private code dataset
    (never in git). None: no copies."""
    try:
        from kaggle_secrets import UserSecretsClient

        url = UserSecretsClient().get_secret("THREADEYE_DATABASE_URL")
    except Exception as exc:  # noqa: BLE001
        found = next(iter(find_inputs("threadeye_db_url.txt", 3)), None)
        url = found.read_text().strip() if found else ""
        print(f"database URL from {'the code dataset' if url else 'nowhere'} (secret: {exc!r:.80})", flush=True)
    # Supabase's transaction pooler (port 6543) stalls on a 70 MB insert (measured from Kaggle: still running
    # after 5 min); its session pooler (5432) takes 31 s. Checkpoint copies go through 5432.
    return url.replace("postgresql+psycopg://", "postgresql://").replace(":6543/", ":5432/") or None


DB_URL = db_url()
if DB_URL:
    subprocess.run([sys.executable, "-m", "pip", "-q", "install", "psycopg[binary]"], check=False)
UPLOAD_KEY = f"models/training/yolox_{SIZE}"


def from_supabase(name: str, dest: Path) -> bool:
    """Download a checkpoint copy a previous session sent to the database."""
    if not DB_URL:
        return False
    try:
        import psycopg

        with psycopg.connect(DB_URL, autocommit=True, prepare_threshold=None, connect_timeout=20) as conn:
            row = conn.execute("SELECT data FROM threadeye.blobs WHERE key = %s", (f"{UPLOAD_KEY}/{name}",)).fetchone()
        if row is None:
            return False
        dest.write_bytes(bytes(row[0]))
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"could not fetch {name} from Supabase: {exc!r:.200}", flush=True)
        return False


# Resume from the newest checkpoint of an earlier session: the other training notebook's output if attached
# (latest_ckpt.pth is written every epoch), otherwise the copy that session sent to Supabase (survives a
# hung or cancelled session, whose output Kaggle does not keep). The optimizer and learning-rate schedule
# continue as they were.
resume_from = run_dir / "resume_from.pth"
prev = sorted([*find_inputs("latest_ckpt.pth", 5), *find_inputs("last_epoch_ckpt.pth", 5)],
              key=lambda p: p.stat().st_mtime)
if INIT_FROM_PREVIOUS:
    RESUME = False
    attached = sorted([*find_inputs("latest_ckpt.pth", 5), *find_inputs("best_ckpt.pth", 5)],
                      key=lambda p: p.stat().st_mtime)
    if not attached:
        raise SystemExit("init_from_previous: no checkpoint attached (attach the previous training notebook)")
    start = f"-c {attached[-1]}"
    print("fine-tuning from the weights of", attached[-1], flush=True)
if RESUME:
    if prev:
        # Only the newest checkpoint: an earlier session's best_ckpt.pth is not copied, it would be an older
        # model than the one this session ends with (session 2 tested session 1's model again because of it).
        shutil.copy(prev[-1], resume_from)
        print("resuming from the attached", prev[-1], flush=True)
    elif from_supabase("latest_ckpt.pth", resume_from):
        print("resuming from Supabase", f"{UPLOAD_KEY}/latest_ckpt.pth", flush=True)
    elif RESUME is True:
        raise SystemExit("resume: no checkpoint attached and none in Supabase")
if resume_from.exists():
    start = f"--resume -c {resume_from}"
gpus = len(subprocess.run("nvidia-smi -L", shell=True, capture_output=True, text=True).stdout.strip().splitlines())
DEVICES = int(PARAMS.get("devices", max(1, gpus)))
print(f"GPUs: {gpus}, training on {DEVICES}, total batch {BATCH}", flush=True)
# Kaggle keeps a session's output only when the script ends without an error: from here on nothing may
# raise. Each step that fails is reported (RUN_STATUS.txt) and the run goes on with what it has.
status: list[str] = []


def note(line: str) -> None:
    print(("!! " if line.startswith("FAILED") else "") + line, flush=True)
    status.append(line)
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "RUN_STATUS.txt").write_text("\n".join(status) + "\n")


# A copy of every new checkpoint goes to the ThreadEye database (Supabase) while training runs: if the session
# then hangs or is killed (Kaggle saves no output for those), the model trained so far is still there.
# Needs the Kaggle secret THREADEYE_DATABASE_URL (Add-ons > Secrets); without it the run goes on without copies.
def checkpoint_uploader(stop: threading.Event) -> None:
    if not DB_URL:
        print("checkpoint copies to Supabase: off", flush=True)
        return
    import psycopg

    url = DB_URL
    seen: dict[str, float] = {}

    def upload_new() -> None:
        for name in ("latest_ckpt.pth", "best_ckpt.pth"):
            f = run_dir / name
            if not f.exists():
                continue
            mtime = f.stat().st_mtime
            if seen.get(name) == mtime or time.time() - mtime < 20:  # unchanged, or still being written
                continue
            data = f.read_bytes()
            key = f"{UPLOAD_KEY}/{name}"
            try:
                with psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=20) as conn:
                    conn.execute("SET statement_timeout = '10min'")
                    conn.execute(
                        "INSERT INTO threadeye.blobs (key, data, sha256, size, content_type) VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT (key) DO UPDATE SET data = excluded.data, sha256 = excluded.sha256, "
                        "size = excluded.size, content_type = excluded.content_type, created_at = now()",
                        (key, data, hashlib.sha256(data).hexdigest(), len(data), "application/octet-stream"),
                    )
                seen[name] = mtime
                print(f"checkpoint copy: {name} ({len(data) / 1e6:.0f} MB) -> Supabase {key}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"checkpoint copy of {name} failed: {exc!r:.200}", flush=True)

    while not stop.wait(90):
        upload_new()
    upload_new()


stop_uploads = threading.Event()
uploader = threading.Thread(target=checkpoint_uploader, args=(stop_uploads,), daemon=True)
if EVAL_ONLY:
    attached = sorted([*find_inputs("latest_ckpt.pth", 5), *find_inputs("best_ckpt.pth", 5)],
                      key=lambda p: p.stat().st_mtime)
    run_dir.mkdir(parents=True, exist_ok=True)
    if attached:
        shutil.copy(attached[-1], run_dir / "latest_ckpt.pth")
        note(f"training: skipped (eval_only); model under test: {attached[-1]}")
else:
    uploader.start()
    try:
        # The variables come first: "timeout VAR=x cmd" would try to run "VAR=x" as the command.
        sh(f"{env} timeout --signal=INT --kill-after=5m {TRAIN_BUDGET_H}h {sys.executable} tools/train.py -f {exp} "
           f"-d {DEVICES} -b {BATCH} --fp16 -o {start}", cwd=YOLOX, name="training",
           limit_min=TRAIN_BUDGET_H * 60 + 10)
        note("training: finished all epochs")
    except subprocess.CalledProcessError as exc:
        note(f"training: stopped (exit {exc.returncode}; 124 = the {TRAIN_BUDGET_H} h budget, 137 = killed after it)")
        # A rank stuck in a GPU collective ignores the interrupt and keeps its GPU memory: clear it before testing.
        subprocess.run("pkill -9 -f tools/train.py", shell=True, check=False)
    stop_uploads.set()
    uploader.join(timeout=600)
# Training evaluates nothing, so the model of this session is its newest checkpoint (latest_ckpt.pth, written at
# the end of every epoch); best_ckpt.pth is only used when there is no newer one.
ckpts = [run_dir / n for n in ("latest_ckpt.pth", "last_epoch_ckpt.pth", "best_ckpt.pth") if (run_dir / n).exists()]
if not ckpts:
    note("FAILED: no checkpoint at all, nothing to evaluate")
    sys.exit(0)
newest = max(ckpts, key=lambda c: c.stat().st_mtime)
if newest != best:
    shutil.copy(newest, best)
note(f"model under test: {newest.name}")

# ------------------------------------------------------------------------------------------- test
def kept(step: str, cmd: str, cwd: Path | None = None) -> None:
    """A step after training: its failure is reported, and the model trained so far is still saved."""
    try:
        sh(cmd, cwd)
    except subprocess.CalledProcessError as exc:
        note(f"FAILED: {step} (exit {exc.returncode}); model kept")


kept("test evaluation", f"THREADEYE_EVAL_SPLIT=test {env} {sys.executable} tools/eval.py -f {exp} -c {best} "
     f"-b {BATCH} -d 1 --conf 0.001 --fp16 2>&1 | tee {TMP / 'test_eval.txt'}", YOLOX)

# ------------------------------------------------------------------------------------------- ONNX
# YOLOX's tools/export_onnx.py calls torch.onnx._export, which recent PyTorch removed. Our own export: raw head
# output (no decoding in the graph: backend/threadeye/providers/local_model.py decodes), dynamic batch (the app
# sends all tiles of a frame at once), the TorchScript exporter (dynamo=False), then a check that ONNX Runtime
# gives the same output as PyTorch on a real test tile.
onnx_path = TMP / f"threadeye_{SIZE}.onnx"
export_py = TMP / "export_onnx.py"
export_py.write_text(f'''
import json, sys
import cv2, numpy as np, onnxruntime as ort, torch
from yolox.data import ValTransform
from yolox.exp import get_exp

exp = get_exp("{exp}", None)
model = exp.get_model()
model.load_state_dict(torch.load("{best}", map_location="cpu", weights_only=False)["model"])
model.eval()
model.head.decode_in_inference = False
torch.onnx.export(model, torch.zeros(1, 3, 640, 640), "{onnx_path}", input_names=["images"], output_names=["output"],
                  opset_version=17, dynamic_axes={{"images": {{0: "batch"}}, "output": {{0: "batch"}}}}, dynamo=False)

test = json.load(open("{WORK / 'annotations/test.json'}"))
name = next(i["file_name"] for i in test["images"] if any(a["image_id"] == i["id"] for a in test["annotations"]))
img, _ = ValTransform(legacy=False)(cv2.imread("{WORK / 'test'}/" + name), None, (640, 640))
x = np.stack([img, img]).astype(np.float32)
with torch.no_grad():
    ref = model(torch.from_numpy(x)).numpy()
got = ort.InferenceSession("{onnx_path}", providers=["CPUExecutionProvider"]).run(None, {{"images": x}})[0]
diff = float(np.abs(ref - got).max())
print("onnx check:", name, got.shape, "max abs diff", diff, flush=True)
sys.exit(0 if diff < 1e-3 else 1)
''')
kept("ONNX export", f"{env} {sys.executable} {export_py}", YOLOX)

# ------------------------------------------------------------------------------- operating point
# COCO AP averages over all thresholds; an inspector sees one. Per-class thresholds are chosen on val (best
# F1) and the test numbers an inspector would see are counted at them (fabricdata/operating.py), per class
# and per source. LocalModelDetector uses these thresholds (model_info.json "thresholds").
dets_py = TMP / "dump_dets.py"
dets_py.write_text(f'''
import json
import cv2, numpy as np, torch
from yolox.data import ValTransform
from yolox.exp import get_exp
from yolox.utils import postprocess

exp = get_exp("{exp}", None)
model = exp.get_model()
model.load_state_dict(torch.load("{best}", map_location="cpu", weights_only=False)["model"])
model.cuda().eval().half()
tf = ValTransform(legacy=False)
for split in ("val", "test"):
    names = [im["file_name"] for im in json.load(open(f"{WORK}/annotations/{{split}}.json"))["images"]]
    out = []
    for i in range(0, len(names), 32):
        chunk, xs, ratios = names[i:i + 32], [], []
        for n in chunk:
            img = cv2.imread(f"{WORK}/{{split}}/{{n}}")
            ratios.append(min(640 / img.shape[0], 640 / img.shape[1]))
            xs.append(tf(img, None, (640, 640))[0])
        with torch.no_grad():
            res = postprocess(model(torch.from_numpy(np.stack(xs)).cuda().half()), exp.num_classes, 0.05, 0.45)
        for n, r, p in zip(chunk, ratios, res):
            if p is None:
                continue
            for x0, y0, x1, y1, obj, cc, c in p.float().cpu().numpy().tolist():
                out.append([n, int(c), obj * cc, [x0 / r, y0 / r, x1 / r, y1 / r]])
    json.dump(out, open(f"{TMP}/dets_{{split}}.json", "w"))
    print(split, len(names), "tiles", len(out), "detections", flush=True)
''')
def operating_point() -> dict[str, float]:
    sh(f"{env} {sys.executable} {dets_py}", cwd=YOLOX)
    sys.path.insert(0, str(find_inputs("fabricdata/operating.py", 4)[0].parents[1]))
    from fabricdata.classes import NUISANCE_CLASSES
    from fabricdata.operating import Det, Truth, choose_thresholds, report

    def load_split(split: str) -> tuple[list, list, list]:
        coco = json.loads((WORK / f"annotations/{split}.json").read_text())
        name_of = {im["id"]: im["file_name"] for im in coco["images"]}
        cname = {c["id"]: c["name"] for c in coco["categories"]}
        truths = [Truth(name_of[a["image_id"]], cname[a["category_id"]],
                        (a["bbox"][0], a["bbox"][1], a["bbox"][0] + a["bbox"][2], a["bbox"][1] + a["bbox"][3]))
                  for a in coco["annotations"]]
        dets = [Det(n, class_names[c], s, tuple(b))
                for n, c, s, b in json.loads((TMP / f"dets_{split}.json").read_text())]
        return dets, truths, list(name_of.values())

    val_dets, val_truths, _ = load_split("val")
    thresholds = choose_thresholds(val_dets, val_truths, class_names)
    test_dets, test_truths, test_images = load_split("test")
    rep = report(test_dets, test_truths, thresholds, set(class_names) - set(NUISANCE_CLASSES),
                 lambda name: name.split("__")[0], test_images)
    rep["thresholds_from"] = "val split, best F1 per class"
    print("thresholds:", thresholds)
    print("test:", json.dumps({k: v for k, v in rep.items() if k not in ("per_class", "per_source")}))
    print("per source:", json.dumps(rep["per_source"], indent=1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "test_report.json").write_text(json.dumps(rep, indent=1))
    return thresholds


# A failure here must not lose a 10-hour model: the checkpoint and ONNX are kept either way.
try:
    thresholds = operating_point()
except Exception as exc:  # noqa: BLE001
    note(f"FAILED: operating point ({exc!r}); no thresholds, model kept")
    thresholds = {}

OUT.mkdir(parents=True, exist_ok=True)
for f in (best, onnx_path, TMP / "test_eval.txt", run_dir / "train_log.txt"):
    if f.exists():
        shutil.copy(f, OUT / f.name)
(OUT / "model_info.json").write_text(json.dumps({
    "framework": "YOLOX (Apache-2.0)", "yolox_commit": commit, "size": SIZE, "epochs": EPOCHS, "batch": BATCH,
    "input": [640, 640], "classes": class_names, "thresholds": thresholds, "run_status": status,
    "dataset_summary": json.loads((ANN / "summary.json").read_text()),
    "minutes": round((time.time() - T0) / 60, 1),
}, indent=1))
print(f"done in {(time.time() - T0) / 60:.1f} min")
