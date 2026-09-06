"""Bind related World/Social/Routines operations to the proposal caller's Session."""
from datetime import date, datetime
from sqlalchemy.orm import Session
from app.domains.worlds.service.character_entry import get_character_entry_world
from app.domains.social.repository.event_evidence import get_post
from app.domains.routines.repository.event_evidence import find_joint_for_proposal
from app.domains.routines.service import joint_activity
from app.domains.routines.policies import planning
from app.runtime.routines.joint_references import SqlAlchemyJointReferences


class SqlAlchemyProposalReferences:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_post(self, post_id: str):
        return get_post(self.db, post_id)

    def get_world(self, world_id: str):
        return get_character_entry_world(self.db, world_id)

    def validate_pair(self, **kwargs):
        return joint_activity.validate_pair(self.db, references=SqlAlchemyJointReferences(self.db), **kwargs)

    def validate_place(self, **kwargs):
        return joint_activity.validate_place(self.db, references=SqlAlchemyJointReferences(self.db), **kwargs)

    def active_commitment_count(self, **kwargs):
        return joint_activity.active_commitment_count(self.db, **kwargs)

    def slot_available(self, **kwargs):
        return joint_activity.slot_available(self.db, references=SqlAlchemyJointReferences(self.db), **kwargs)

    def create_scheduled_joint(self, **kwargs):
        return joint_activity.create_scheduled_joint(self.db, references=SqlAlchemyJointReferences(self.db), **kwargs)

    def find_joint_for_proposal(self, proposal_id: str):
        return find_joint_for_proposal(self.db, proposal_id=proposal_id)

    def local_activity_date(self, now: datetime, timezone_name: str):
        return planning.local_activity_date(now, timezone_name)

    def daypart_windows(self, local_date: date, timezone_name: str):
        return planning.daypart_windows(local_date, timezone_name)
