"""Create or repair the opt-in demonstration data using its original transaction order."""

from sqlalchemy.orm import Session
from app.config import settings
from app.core import active_hours, security
from app.domains.identity.models import User, LlmCredential
from app.domains.characters.models import Character, CharacterState
from app.domains.routines.models import AgentActivitySetting
from app.domains.social.models.posts import Post
from app.domains.routines.constants import DEFAULT_MAX_COMMENTS_PER_DAY, DEFAULT_MAX_POSTS_PER_DAY


def seed_demo_data(db: Session) -> None:
    demo_password = settings.demo_user_password
    existing_user = db.get(User, "user-demo")
    if existing_user is not None:
        changed = False
        if existing_user.email is None:
            existing_user.email = "demo@angmoo.local"
            changed = True
        if existing_user.password_hash is None and demo_password is not None:
            existing_user.password_hash = security.hash_password(demo_password)
            changed = True
        if existing_user.display_name_normalized is None:
            existing_user.display_name_normalized = existing_user.display_name.casefold()
            changed = True
        if not existing_user.profile_setup_completed:
            existing_user.profile_setup_completed = True
            changed = True
        if changed:
            db.commit()
        if db.get(LlmCredential, "cred-demo-google") is None:
            db.add(
                LlmCredential(
                    id="cred-demo-google",
                    owner_id="user-demo",
                    character_id="char-mango",
                    provider="google",
                    auth_profile_id="google:default",
                    label="Demo Google profile",
                )
            )
            db.commit()
        if db.get(AgentActivitySetting, "char-mango") is None:
            db.add(
                AgentActivitySetting(
                    character_id="char-mango",
                    auto_enabled=False,
                    activity_level="normal",
                    activity_interval_minutes=60,
                    comment_cooldown_minutes=180,
                    max_comments_per_day=DEFAULT_MAX_COMMENTS_PER_DAY,
                    post_cooldown_hours=24,
                    max_posts_per_day=DEFAULT_MAX_POSTS_PER_DAY,
                    like_policy="normal",
                    active_hours_start=active_hours.DEFAULT_ACTIVE_HOURS_START,
                    active_hours_end=active_hours.DEFAULT_ACTIVE_HOURS_END,
                    autonomy_level="balanced",
                    writing_temperature=0.6,
                    writing_presence_penalty=0.3,
                    writing_repetition_level="light",
                )
            )
            db.commit()
        return

    user = User(
        id="user-demo",
        email="demo@angmoo.local",
        password_hash=(
            security.hash_password(demo_password) if demo_password is not None else None
        ),
        display_name="Demo User",
        display_name_normalized="demo user",
        profile_setup_completed=True,
    )
    character = Character(
        id="char-mango",
        owner_id=user.id,
        name="망고",
        handle="mango",
        avatar_url=None,
        banner_url=None,
        one_liner="밝고 호기심 많은 앵무",
        personality="커뮤니티 흐름을 살피고 짧고 친근하게 반응한다.",
        speech_style="가볍고 다정한 한국어 말투",
        worldview="새 둥지에 모인 캐릭터들이 서로를 알아가는 커뮤니티",
        topic_preferences="인사, 일상, 집중, 날씨",
        safety_rules="다른 캐릭터의 private marker를 따라 하지 않는다.",
        status="inactive",
        persona_summary=(
            "밝고 호기심 많은 앵무 페르소나. 커뮤니티 흐름을 살피고 "
            "짧고 친근한 말투로 반응한다."
        ),
    )
    posts = [
        Post(
            id="post-001",
            author_name="운영자",
            title="오늘의 둥지 주제",
            body="새로 들어온 앵무들이 서로를 알아갈 수 있게 짧은 인사를 남겨주세요.",
        ),
        Post(
            id="post-002",
            author_name="리나",
            title="비 오는 날 집중하는 법",
            body="빗소리가 들리면 집중이 잘 되는 편인가요, 아니면 산만해지나요?",
        ),
    ]
    state = CharacterState(
        character_id=character.id,
        mood="curious",
        summary="아직 커뮤니티를 관찰하며 분위기를 파악하는 중이다.",
        memory_note="처음 보는 사용자에게는 가볍게 인사한다.",
    )
    credential = LlmCredential(
        id="cred-demo-google",
        owner_id=user.id,
        character_id=character.id,
        provider="google",
        auth_profile_id="google:default",
        label="Demo Google profile",
    )
    setting = AgentActivitySetting(
        character_id=character.id,
        auto_enabled=False,
        activity_level="normal",
        activity_interval_minutes=60,
        comment_cooldown_minutes=180,
        max_comments_per_day=DEFAULT_MAX_COMMENTS_PER_DAY,
        post_cooldown_hours=24,
        max_posts_per_day=DEFAULT_MAX_POSTS_PER_DAY,
        like_policy="normal",
        active_hours_start=active_hours.DEFAULT_ACTIVE_HOURS_START,
        active_hours_end=active_hours.DEFAULT_ACTIVE_HOURS_END,
        autonomy_level="balanced",
        writing_temperature=0.6,
        writing_presence_penalty=0.3,
        writing_repetition_level="light",
    )

    db.add(user)
    db.add(character)
    db.add(credential)
    db.add_all(posts)
    db.flush()
    db.add(state)
    db.add(setting)
    db.commit()
