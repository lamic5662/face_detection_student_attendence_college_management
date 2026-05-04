from datetime import UTC, date, datetime, time


def utc_now_naive() -> datetime:
    """Return current UTC time as a naive datetime for DB compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)


def utc_today() -> date:
    return utc_now_naive().date()


def utc_time_now() -> time:
    return utc_now_naive().time()
