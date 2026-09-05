"""Small Social formatting helpers without persistence or policy decisions."""





def _parse_int_cursor(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
