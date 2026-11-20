# Operational Visualization

Created: 2026-11-20

Add four charts to existing pages without changing business decisions or access:
Dashboard verdict donut (Recharts), mill monthly quality trend (Chart.js),
confirmed defect class/yard-position heatmap (ECharts), and model benchmark
comparisons (Plotly). Existing custom cutting maps remain unchanged.

Use current API data only; null means unavailable, never zero. Dataset benchmark
precision is not supplied, so compare localization/class recall by dataset and
precision/recall by class. Grouped supplier trends weight each month by that
month's inspected rolls. Preserve gaps and a clearly labeled existing reference
of 40 points (not a claim of a universal buyer limit).

All charts support English/Bangla, light/dark, narrow layouts, visible empty
states, exact numeric alternatives and teardown on navigation. Bundle locally
for offline use; load plotting code only on the pages that use it.
