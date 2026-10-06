"""Project already-visible World posts with one typed author read per World."""
from collections import defaultdict
from app.domains.social.contracts.post_authors import PostAuthorReferences


def read_post_author_profiles(*, references: PostAuthorReferences, posts):
    worlds = defaultdict(set)
    for post in posts:
        if post.world_id and post.author_world_character_id:
            worlds[post.world_id].add(post.author_world_character_id)
    profiles = {}
    for world_id, author_ids in worlds.items():
        profiles.update(references.author_profiles(world_id=world_id, author_ids=author_ids))
    return profiles


def enrich_post_authors(*, references: PostAuthorReferences, views):
    world_views = defaultdict(list)
    for item in views:
        if item.world_id and item.author_world_character_id:
            world_views[item.world_id].append(item)
        for reference in (getattr(item, "quoted_post", None), getattr(item, "reposted_post", None)):
            if reference is not None and reference.world_id and reference.author_world_character_id:
                world_views[reference.world_id].append(reference)
    for world_id, items in world_views.items():
        profiles = references.author_profiles(world_id=world_id,
            author_ids={item.author_world_character_id for item in items})
        for item in items:
            profile = profiles.get(item.author_world_character_id)
            if (profile is None or profile.world_id != item.world_id or
                profile.world_character_id != item.author_world_character_id or
                profile.character_id != item.author_character_id or getattr(item, "author_deleted", False)):
                continue
            item.author_name = profile.display_name
            item.author_handle = profile.handle
            item.author_avatar_url = profile.avatar_url
