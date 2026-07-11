from datetime import datetime, time, timedelta, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_day_bounds_utc(date_str: str) -> tuple[str, str]:
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    local_tz = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(target_date, time.min, tzinfo=local_tz)
    end_local = datetime.combine(
        target_date + timedelta(days=1),
        time.min,
        tzinfo=local_tz,
    )
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


