# Realtime channel contract (v0)

Defined in PLAN.md §5.1. Schemas: `backend/threadeye/api/schemas/events.py` (exported in
`docs/api/openapi.json` as `EventEnvelope` / `EventsPage`). Built in M2.

- **Durable events** are appended to `inspection_events` with a per-inspection `seq` (1, 2, 3, …) in
  the same transaction as the projections they change.
- **Transports:** SSE `GET /api/v1/inspections/{id}/stream` (edge; resume with `Last-Event-ID` = seq);
  polling `GET /api/v1/inspections/{id}/events?after_seq=N` (cloud and fallback); and the events
  returned by `POST /api/v1/inspections/{id}/advance`.
- **Clients apply events idempotently by `seq`.** Bootstrap with `GET /api/v1/inspections/{id}` (has
  `last_seq`), then subscribe with `after_seq = last_seq`.
- **Ephemeral** messages (`machine.tick`, `heartbeat`) carry no `seq` and are not stored. They are only
  needed for server-clocked sources (future webcam).
- Every envelope carries `simulated` and `provider` so the UI can never show simulated detections
  unlabelled.

```json
{"v":1,"inspection_id":"0192…","seq":1042,"type":"defect.upserted",
 "at":"2026-10-20T04:15:22.123Z","actor":{"kind":"engine"},
 "simulated":true,"provider":"simulated@0.1.0","payload":{"defect":{}, "change":"created"}}
```
