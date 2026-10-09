# SwiftLine tracking webhooks — integration spec

SwiftLine POSTs tracking events to our endpoint. This document is the contract; implement
`tracking.py` to it.

## 1. Authenticity

Every request carries two headers:

- `X-Swift-Timestamp`: Unix time in seconds when SwiftLine sent the request.
- `X-Swift-Signature`: `v1=` followed by the lowercase hex HMAC-SHA256 of the bytes
  `"{timestamp}." + raw_body`, keyed with our shared secret.

A request is authentic only if:

1. the signature header starts with `v1=` and the digest matches (compare in constant time);
2. the timestamp is within **300 seconds** of our clock, in either direction.

Anything else is rejected, and its events are not processed.

## 2. Events

An event is a JSON object:

```json
{"event_id": "evt_01", "shipment_id": "SL4410001", "status": "in_transit",
 "occurred_at": "2026-10-08T09:15:00+08:00"}
```

`occurred_at` is ISO 8601 **with a UTC offset**. Hubs report in local time, so two events for one
shipment may carry different offsets.

Known statuses: `label_created`, `picked_up`, `in_transit`, `out_for_delivery`,
`delivery_failed`, `delivered`, `returned`.

## 3. Processing rules

Events can arrive late, out of order, and more than once. For each event, in this order:

1. **Duplicate.** An `event_id` already seen is a duplicate: no effect.
2. **Unknown status.** A status not in the list above is ignored: no effect (the event id still
   counts as seen).
3. **Stale.** An event that occurred **earlier** than the shipment's current status is stale: no
   effect. An event at the same instant as the current status is applied.
4. **Terminal.** `delivered` and `returned` are terminal. After `delivered`, only `returned` may
   follow; after `returned`, nothing may. A later event that breaks this is ignored.
5. Otherwise the event is **applied**: it becomes the shipment's current status.

`Tracker.handle()` returns what happened: `"applied"`, `"duplicate"`, `"ignored"` or `"stale"`.
