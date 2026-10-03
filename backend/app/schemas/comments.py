from __future__ import annotations

from datetime import datetime

from app.schemas.common import ApiModel


class CommentOut(ApiModel):
    id: int
    author: str
    author_is_uploader: bool
    author_is_verified: bool
    text: str
    like_count: int | None
    published_at: datetime | None
    is_pinned: bool
    is_favorited: bool


class CommentThread(CommentOut):
    replies: list[CommentOut]


class CommentsPage(ApiModel):
    items: list[CommentThread]
    total: int  # top-level comments saved
    saved: int  # all saved comments, replies included
    comment_count: int | None  # how many YouTube counted
    fetched_at: datetime | None
    fetching: bool
    error: str | None
