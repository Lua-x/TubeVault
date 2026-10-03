"""Comments saved with a video – optional, read offline."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, func, select

from app.core.deps import AdminUser, Context, CurrentUser, DbSession
from app.models import Comment, User, Video
from app.schemas.comments import CommentOut, CommentsPage, CommentThread
from app.services.access import ensure_visible, require_can_add
from app.services.app_settings import load_app_settings

router = APIRouter(prefix="/videos", tags=["comments"])

CommentSort = Literal["top", "new"]


def _video(db: DbSession, video_id: int, user: User) -> Video:
    return ensure_visible(user, db.get(Video, video_id))


def _page(db: DbSession, ctx: Context, video: Video, items: list[CommentThread]) -> CommentsPage:
    counts = db.execute(
        select(
            func.count(Comment.id).filter(Comment.parent_id.is_(None)),
            func.count(Comment.id),
        ).where(Comment.video_id == video.id)
    ).one()
    fetching, error = ctx.comments.state(video.id)
    return CommentsPage(
        items=items,
        total=counts[0],
        saved=counts[1],
        comment_count=video.comment_count,
        fetched_at=video.comments_fetched_at,
        fetching=fetching,
        error=error,
    )


@router.get("/{video_id}/comments")
def list_comments(
    video_id: int,
    user: CurrentUser,
    db: DbSession,
    ctx: Context,
    sort: CommentSort = "top",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> CommentsPage:
    video = _video(db, video_id, user)
    query = select(Comment).where(Comment.video_id == video.id, Comment.parent_id.is_(None))
    if sort == "new":
        query = query.order_by(Comment.published_at.desc().nulls_last(), Comment.position)
    else:
        query = query.order_by(Comment.is_pinned.desc(), Comment.position)
    roots = db.scalars(query.offset(offset).limit(limit)).all()
    replies: dict[str, list[CommentOut]] = {}
    if roots:
        for reply in db.scalars(
            select(Comment)
            .where(
                Comment.video_id == video.id,
                Comment.parent_id.in_([root.youtube_id for root in roots]),
            )
            .order_by(Comment.position)
        ):
            assert reply.parent_id is not None
            replies.setdefault(reply.parent_id, []).append(CommentOut.model_validate(reply))
    items = [
        CommentThread(
            **CommentOut.model_validate(root).model_dump(),
            replies=replies.get(root.youtube_id, []),
        )
        for root in roots
    ]
    return _page(db, ctx, video, items)


@router.post("/{video_id}/comments", status_code=status.HTTP_202_ACCEPTED)
def fetch_comments(video_id: int, user: CurrentUser, db: DbSession, ctx: Context) -> CommentsPage:
    """Loads (or refreshes) the comments from YouTube in the background."""
    require_can_add(user)
    video = _video(db, video_id, user)
    ctx.comments.request(video.id, load_app_settings(db).downloads.max_comments)
    return _page(db, ctx, video, [])


@router.delete("/{video_id}/comments", status_code=status.HTTP_204_NO_CONTENT)
def delete_comments(video_id: int, user: AdminUser, db: DbSession) -> None:
    video = _video(db, video_id, user)
    db.execute(delete(Comment).where(Comment.video_id == video.id))
    video.comments_fetched_at = None
    video.comment_count = None
    db.commit()
