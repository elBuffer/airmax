def deduplicate(readings):
    seen = set()
    for reading in readings:
        key = reading.location_id, reading.pollutant, reading.source_time
        if key not in seen:
            seen.add(key)
            yield reading
