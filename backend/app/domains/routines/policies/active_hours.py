DEFAULT_ACTIVE_HOURS_START = "14:00"
DEFAULT_ACTIVE_HOURS_END = "22:00"
MAX_ACTIVE_HOURS_MINUTES = 17 * 60
ACTIVE_HOURS_LIMIT_MESSAGE = "활동 시간은 최대 17시간까지 설정할 수 있습니다."


def parse_active_hour(value: str, *, allow_end_of_day: bool) -> int:
    if allow_end_of_day and value == "24:00":
        return 24 * 60
    parts = value.split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise ValueError(ACTIVE_HOURS_LIMIT_MESSAGE)
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute not in {0, 30}:
        raise ValueError(ACTIVE_HOURS_LIMIT_MESSAGE)
    return hour * 60 + minute


def active_hours_minutes(start_value: str, end_value: str) -> tuple[int, int]:
    return (
        parse_active_hour(start_value, allow_end_of_day=False),
        parse_active_hour(end_value, allow_end_of_day=True),
    )


def active_hours_duration_from_minutes(start: int, end: int) -> int:
    if start == end:
        return 0
    return (end - start) % (24 * 60)


def active_hours_duration_minutes(start_value: str, end_value: str) -> int:
    start, end = active_hours_minutes(start_value, end_value)
    return active_hours_duration_from_minutes(start, end)


def validate_active_hours(start_value: str, end_value: str) -> None:
    duration = active_hours_duration_minutes(start_value, end_value)
    if duration <= 0 or duration > MAX_ACTIVE_HOURS_MINUTES:
        raise ValueError(ACTIVE_HOURS_LIMIT_MESSAGE)
