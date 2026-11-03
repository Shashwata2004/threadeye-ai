# KPI definitions

Dashboard time boundary: the current day in Asia/Dhaka. Each roll contributes only its latest finalized
inspection within that day. Inspector accounts see their own work; supervisor/management/admin can see
the broader scope. Archived sample deliveries are excluded. Saved sample inspections are labelled as
simulated-source activity; they do not establish factory impact.

| Metric | Definition |
|---|---|
| Rolls inspected | Count of rolls with a finalized inspection in the selected scope/day |
| Verdict distribution | System PASS/BORDERLINE/FAIL, before any supervisor commercial override |
| Average points / 100 sq yd | Arithmetic mean of those inspections' normalized 4-point scores |
| Coverage | Mean of the latest recorded pipeline coverage percentage for those inspections |
| Rejected share of reviewed AI flags | Inspector-rejected detector-origin flags / reviewed detector-origin flags; manual additions excluded. Not an independently measured false-positive rate |
| Top defect types | Confirmed, scored-kind defects on the selected finalized inspections |
| By machine/mill | Counts of the selected rolls grouped by machine or supplier |
| Today's verification | Latest run today per machine: queued/running, GREEN if tolerances pass, RED if they fail; no run is AMBER. A passed machine does not certify unchecked machines |

Reference checks record recall, false alarms and absolute normalized-score difference against the known
answer key. Their editable tolerances are stored per run. A reference-video check verifies software
behaviour on known data; it is not a physical camera-health guarantee. A RED result warns on the live
inspection screen; the human remains responsible for decisions.

Benchmarks require a locally curated held-out test manifest and refuse train/validation data. Preserve
source-group exclusion evidence alongside that manifest. The repeatedly used demo roll is a regression
fixture, not a fresh blind evaluation. Simulated baseline and real-model results must retain different
labels. Headless processing seconds exclude network, browser and human review.

Factory impact definitions and paired-measurement collection: [impact/PILOT_PROTOCOL.md](impact/PILOT_PROTOCOL.md).
No financial/yield improvement is derived from model recall or a cutting-sheet preview alone.
