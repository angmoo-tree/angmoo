"""Stable revision of a post title/body pair, with no I/O."""
from hashlib import sha256

def post_revision(post):
    return sha256(((post.title or "") + "\n" + (post.body or "")).encode()).hexdigest()
