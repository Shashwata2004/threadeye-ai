# Demo script v1 (M2): one roll's journey, about 3 minutes

Setting: the edge laptop, **Wi-Fi off** (`make up` was run earlier). Browser at http://localhost:8080.
Everything on screen says SIMULATED: the camera feed is the simulator's video and the detector reads
the simulator's answer key. Say so out loud once, at the start.

| # | Time | Who / screen | Do | Say |
|---|---|---|---|---|
| 1 | 0:00 | Banner | Point at the amber banner and the detector badge | "This build runs on a simulated camera and a simulated detector. It is not our AI yet; our own model arrives in M6. Everything you see is labelled." |
| 2 | 0:15 | `store` · Deliveries & rolls | Open the prepared challan, show its rolls and a printed QR label | "The store registers the mill's delivery. Each roll gets a QR label." |
| 3 | 0:35 | `inspector` · Inspect a roll | Scan/type the roll code, preset *realistic*, **Load roll**, **Start** at 2× | "The inspector loads the roll on the machine they already own. The camera watches the fabric." |
| 4 | 0:50 | Live screen | Let it run; point at a red box moving with the fabric, the yard tape, speed, the machine stop | "Boxes are in roll coordinates, so they stay on the defect as the fabric moves. The counter is yards inspected." |
| 5 | 1:20 | Live screen | On a false alarm (sticker / thread): **X**, pick the reason. On a real one: **C** | "The detector is not trusted blindly: one key confirms, one key rejects, and the reason becomes training data." |
| 6 | 1:45 | Points meter | Point at the points against the roll's budget and the per-100 colour | "The 4-point score is live, under the buyer's own rule profile." |
| 7 | 2:05 | End of roll | **Finish roll**, clear the last pending defects, **Compute verdict** | "No verdict while anything is undecided." |
| 8 | 2:20 | Verdict page | Verdict badge, per-yard points with the cap, roll map; click a defect for its photo | "Every point has a reason the supervisor can check." |
| 9 | 2:40 | `supervisor` · Verdict | For BORDERLINE: choose *Accept with a claim*, type a reason, record | "Humans decide the money questions; the change ledger records who and why." |
| 10 | 2:50 | Report PDF | Open the Bangla or English PDF | "The report goes to the mill. It says SIMULATED until the real model is in." |

**Power-cut moment (optional, +30 s):** during step 4 close the tab (or stop the API container), reopen
the live screen: "Inspection stopped by a power cut. No data was lost." → **Resume from x yd**.

Backup: if the live run misbehaves, open a finished inspection's verdict page (prepared before the demo).
