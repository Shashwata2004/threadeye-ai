# Plan

Reuse existing API contracts and permission-gated page data. Add client-only lazy
chart components with theme-aware palettes and accessible tables. Import only
needed Chart.js/ECharts modules and the basic Plotly bundle. No database/schema
or scoring change. Heatmap counts confirmed defect centers once, bounds bins and
excludes rejected/nondefect entries. Protect against async rendering after unmount.

Constitution review: no new inference or claims, decisions preserved, source data
unchanged, backend permissions unchanged, local dependencies support offline edge,
and plots distinguish missing data from measured zero. Check frontend/static
build and browser interactions using isolated mocked API fixtures.
