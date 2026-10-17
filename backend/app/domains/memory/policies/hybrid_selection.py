"""Preserve canonical fusion order; deduplicate only after authorization."""
def selection_steps(request, records):
    steps, seen = [], set()
    for record in records:
        key = record.memory_item_id or record.reference
        steps.append((record, key not in seen))
        seen.add(key)
        if len(seen) >= request.result_limit:
            break
    return tuple(steps)


def select_records(request, records):
    return tuple(record for record, selected in selection_steps(request, records) if selected)
