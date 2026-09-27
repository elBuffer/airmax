from datetime import datetime, timedelta


def rolling_window(
    latest_received: datetime | None, hours: int
) -> tuple[datetime | None, datetime | None]:
    if latest_received is None:
        return None, None
    return latest_received - timedelta(hours=hours), latest_received


def within_window(readings, start: datetime, end: datetime):
    return (reading for reading in readings if start <= reading.sent_at <= end)
