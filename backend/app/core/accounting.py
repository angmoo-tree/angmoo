"""Pure calendar predicates; the calling domain retains its quota SQL."""
from sqlalchemy import and_, or_


def in_accounting_period(column, period):
    return or_(*(and_(column >= start, column < end) for start, end in period.ranges))
