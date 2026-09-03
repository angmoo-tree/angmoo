"""Revalidate one immutable Today snapshot without adding later activities."""

from sqlalchemy.orm import Session

from app.domains.chat.application.today_sns_activity import TodaySnsActivityAssembler
from app.domains.chat.domain.today_sns_activity import TodaySnsActivitySnapshot
from app.domains.chat.ports.today_sns_activity import TodaySnsSnapshotChangedError
from app.runtime.social.sqlalchemy_today_activity import SqlAlchemyTodaySocialActivityReader


class SqlAlchemyTodaySnsSnapshotValidator:
    def __init__(self, db: Session, character_labels: dict[str, str]) -> None:
        self._assembler = TodaySnsActivityAssembler(SqlAlchemyTodaySocialActivityReader(db))
        self._character_labels = dict(character_labels)

    def assert_current(self, snapshot: TodaySnsActivitySnapshot) -> None:
        try:
            current = self._assembler.assemble(
                owner_id=snapshot.owner_id,
                world_id=snapshot.world_id,
                subject_world_character_id=snapshot.subject_world_character_id,
                timezone=snapshot.timezone,
                character_labels=self._character_labels,
                now=snapshot.complete_through,
            )
        except Exception as exc:
            raise TodaySnsSnapshotChangedError("today_sns_snapshot_unavailable") from exc
        if current.snapshot_hash != snapshot.snapshot_hash:
            raise TodaySnsSnapshotChangedError("today_sns_snapshot_changed")
