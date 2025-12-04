# Metrics Recalculation Integration (MR)

## Overview
The **Metrics Recalculation Integration** ensures that when historical data is recovered by the Data Recoverer (DR), the corresponding quality metrics are automatically updated. 

Instead of re-implementing calculation logic, this module leverages the existing **LD Eval** service. It acts as a bridge, notifying LD Eval of every recovered event so that the evaluation service can perform its standard recalculation process.

---

## Strategy

### Reuse of LD Eval
**LD Eval** is already capable of:
1.  Mapping events to metrics.
2.  Recalculating metrics based on the full history of data.
3.  Handling idempotent updates.

Therefore, **LD Connect** does not need to know *how* to calculate metrics, only *when* new data is available.

---

## Subcomponents

### MR1 - Notification Trigger
**Objective:** Notify LD Eval immediately after a recovered event is successfully persisted.

**Tasks:**
- Integrate with `DataRecoverer._persist_batch`.
- For each inserted/updated document, extract:
    - `event_type` (e.g., "push", "task")
    - `prj` (Project ID)
    - `author_login` (User ID)
- Send a standard `POST /api/event` request to LD Eval.

**Dependencies:** `DR` (Data Recoverer).

---

## Implementation Details

### Integration Point
The logic is embedded directly within `LD_Connect_Event/data_recoverer/DR_recovery.py`.

```python
# Pseudo-code for integration
def _persist_batch(self, batch):
    # ... write to MongoDB ...
    
    for doc in batch.documents:
        notify_eval_push(
            event_type=doc["event_type"],
            prj=doc["prj"],
            author_login=doc["author_login"]
        )
```

### Performance Considerations
- **Sequential Notification:** The current design notifies LD Eval sequentially for each event.
- **Asynchronous Processing:** LD Eval handles the actual calculation in a background thread, so the HTTP request from LD Connect returns immediately (`200 OK`), minimizing the delay during recovery.

---

## Expected Deliverables
- **Code Changes:** Modification of `DR_recovery.py` to import and call `notify_eval_push`.
- **Tests:** `test_DR_notification.py` to verify that notifications are sent with the correct payload.
