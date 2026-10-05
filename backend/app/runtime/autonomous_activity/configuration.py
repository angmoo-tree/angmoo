"""Use the accepted run's immutable World values, including recovery attempts."""
from app.runtime.world_configuration.effective_values import configuration_for_input, configured_character
from dataclasses import dataclass
from app.runtime.social.world_feed_queries import WorldFeedQueries


def configuration_for_activity(ctx, actor):
    snapshot = getattr(ctx, "input_snapshot", None)
    if not snapshot or "_world_configuration" not in snapshot:
        return None
    configuration = configuration_for_input(snapshot, character_id=ctx.character.id)
    if configuration is not None and (configuration.world_id, configuration.world_character_id) != (actor.world_id, actor.id):
        raise ValueError("world_configuration_snapshot_scope_invalid")
    return configuration


def character_for_activity(ctx, actor):
    return configured_character(ctx.character, configuration_for_activity(ctx, actor))


def accepted_autonomy(ctx, actor):
    """The admission already chose ON/manual; current access remains canonical."""
    configuration = configuration_for_activity(ctx, actor)
    if configuration is None:
        return actor.autonomous_enabled
    from app.runtime.routines.activity_policy import is_manual_policy_session
    return configuration.autonomous_enabled or is_manual_policy_session(ctx.session_key)


@dataclass(frozen=True)
class AcceptedActivityActor:
    source: object
    autonomous_enabled: bool

    def __getattr__(self, name):
        # Membership, role, publication status and deletion are still live
        # canonical checks. Only the already accepted autonomy choice is frozen.
        return getattr(self.source, name)


class ActivityFeedQueries(WorldFeedQueries):
    def __init__(self, ctx, actor):
        super().__init__(ctx.db)
        self.ctx, self.actor = ctx, actor

    def world_character(self, identity):
        row = super().world_character(identity)
        if row is not None and identity == self.actor.id and configuration_for_activity(self.ctx, self.actor) is not None:
            return AcceptedActivityActor(row, accepted_autonomy(self.ctx, self.actor))
        return row
