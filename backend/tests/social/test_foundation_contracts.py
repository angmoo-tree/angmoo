"""Registry identity across the Social move and immutable migration imports."""
from app import models as registered
from app.core.db import Base
from app.domains.social import public
from app.domains.social.contracts import subjective_context, today_activity, writes
from app.domains.social.infrastructure import sqlalchemy_subjective_context_models as historical
from app.domains.social.models import feed, manual_writes, posts, subjective_context as context_models


def test_all_social_models_share_registered_metadata_and_original_tables():
    groups = {
        posts: ("Post", "PostMedia", "PostImageGenerationJob", "PostImageQuotaReservation", "PostLike", "PostRepost", "PostReport", "Comment", "ProfileFollow", "Notification"),
        feed: ("WorldCharacterFeedCursor", "WorldCharacterFeedObservation", "WorldCharacterBlock"),
        manual_writes: ("OwnerManualSocialWrite", "OwnerManualInboxCandidate"),
        context_models: ("SocialActionSubjectiveContext",),
    }
    for module, names in groups.items():
        for name in names:
            model = getattr(module, name)
            assert getattr(registered, name) is model
            assert model.metadata is Base.metadata
            assert Base.metadata.tables[model.__tablename__] is model.__table__
            assert model.__module__ == module.__name__
    assert posts.Post.comments.property.mapper.class_ is posts.Comment
    assert posts.Post.likes.property.mapper.class_ is posts.PostLike
    assert posts.Post.media.property.mapper.class_ is posts.PostMedia
    assert posts.Post.repost_events.property.mapper.class_ is posts.PostRepost


def test_frozen_subjective_migration_and_public_values_keep_single_definitions():
    assert historical.SocialActionSubjectiveContext is context_models.SocialActionSubjectiveContext
    assert historical.create_subjective_context_schema is context_models.create_subjective_context_schema
    assert historical.drop_subjective_context_schema is context_models.drop_subjective_context_schema
    assert historical.SUBJECTIVE_CONTEXT_SCHEMA_TABLES == ("social_action_subjective_contexts",)
    assert public.ActionSubjectiveContextV1 is subjective_context.ActionSubjectiveContextV1
    assert public.SubjectiveContextContractError is subjective_context.SubjectiveContextContractError
    assert public.TodaySocialActivityRead is today_activity.TodaySocialActivityRead
    assert public.OwnerPostCommand is writes.OwnerPostCommand
    assert public.SocialWriteError is writes.SocialWriteError
