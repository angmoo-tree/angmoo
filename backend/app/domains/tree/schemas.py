from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TreeCategory = Literal["notice", "bug", "suggestion", "question", "free"]


class TreeAuthorRead(BaseModel):
    id: str
    display_name: str
    handle: str | None = None
    avatar_url: str | None = None


class TreeRelatedCharacterRead(BaseModel):
    id: str
    name: str
    handle: str | None = None
    avatar_url: str | None = None


class TreePostCreate(BaseModel):
    category: TreeCategory
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    related_character_id: str | None = Field(default=None, max_length=64)


class TreeCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class TreeCommentRead(BaseModel):
    id: int
    post_id: str
    author: TreeAuthorRead
    content: str
    created_at: datetime


class TreePostSummary(BaseModel):
    id: str
    category: TreeCategory
    title: str
    body: str
    author: TreeAuthorRead
    related_character: TreeRelatedCharacterRead | None = None
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime


class TreePostDetail(TreePostSummary):
    comments: list[TreeCommentRead] = []


class TreeFeedPage(BaseModel):
    items: list[TreePostSummary]
    next_cursor: str | None = None
