"""The signed-in user's own folders for sorting videos – with folders inside folders."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession
from app.models import Folder, FolderItem, User, Video, VideoStatus
from app.schemas.folders import FolderCrumb, FolderDetail, FolderIn, FolderOut, FolderUpdate
from app.services.access import ensure_visible, visible_videos
from app.services.presenters import video_summaries

router = APIRouter(prefix="/folders", tags=["folders"])

# Deep enough for any sorting, shallow enough that a path still fits on a phone.
MAX_DEPTH = 10


def _get(db: DbSession, user: User, folder_id: int) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None or folder.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ordner nicht gefunden")
    return folder


def _videos(db: DbSession, user: User, folder_id: int, limit: int | None = None) -> list[Video]:
    query = (
        visible_videos(select(Video), user)
        .join(FolderItem, FolderItem.video_id == Video.id)
        .where(FolderItem.folder_id == folder_id, Video.status == VideoStatus.READY)
        .options(selectinload(Video.channel))
        .order_by(func.lower(Video.title), Video.id)
    )
    return list(db.scalars(query.limit(limit) if limit else query))


def _path(db: DbSession, folder: Folder) -> list[Folder]:
    """The folders above `folder`, from the top down."""
    above: list[Folder] = []
    parent_id = folder.parent_id
    while parent_id is not None and len(above) <= MAX_DEPTH:
        parent = db.get(Folder, parent_id)
        if parent is None:
            break
        above.insert(0, parent)
        parent_id = parent.parent_id
    return above


def _out(
    db: DbSession,
    user: User,
    folder: Folder,
    *,
    subfolders: int,
    video_id: int | None = None,
) -> FolderOut:
    out = FolderOut.model_validate(folder)
    out.video_count = (
        db.scalar(
            visible_videos(select(func.count(Video.id)), user)
            .join(FolderItem, FolderItem.video_id == Video.id)
            .where(FolderItem.folder_id == folder.id, Video.status == VideoStatus.READY)
        )
        or 0
    )
    out.folder_count = subfolders
    out.cover = video_summaries(db, user.id, _videos(db, user, folder.id, limit=4))
    if video_id is not None:
        out.contains = (
            db.scalar(
                select(FolderItem.id).where(
                    FolderItem.folder_id == folder.id, FolderItem.video_id == video_id
                )
            )
            is not None
        )
    return out


def _children(db: DbSession, user: User) -> Counter[int | None]:
    return Counter(db.scalars(select(Folder.parent_id).where(Folder.user_id == user.id)))


def _check_name(
    db: DbSession, user: User, name: str, parent_id: int | None, own: int | None
) -> None:
    siblings = db.scalars(
        select(Folder).where(
            Folder.user_id == user.id,
            Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id,
        )
    )
    if any(f.name.casefold() == name.casefold() and f.id != own for f in siblings):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Hier gibt es schon einen Ordner „{name}“.")


def _check_parent(db: DbSession, user: User, parent_id: int | None, moving: Folder | None) -> None:
    if parent_id is None:
        return
    parent = _get(db, user, parent_id)
    chain = [*_path(db, parent), parent]
    if moving is not None and any(f.id == moving.id for f in chain):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Ein Ordner kann nicht in sich selbst liegen."
        )
    if len(chain) >= MAX_DEPTH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Ordner gehen höchstens {MAX_DEPTH} Ebenen tief."
        )


@router.get("")
def list_folders(user: CurrentUser, db: DbSession, video_id: int | None = None) -> list[FolderOut]:
    """All of the user's folders, flat – parent_id gives the tree."""
    children = _children(db, user)
    folders = db.scalars(
        select(Folder).where(Folder.user_id == user.id).order_by(func.lower(Folder.name))
    )
    return [_out(db, user, f, subfolders=children[f.id], video_id=video_id) for f in folders]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_folder(body: FolderIn, user: CurrentUser, db: DbSession) -> FolderOut:
    _check_parent(db, user, body.parent_id, None)
    _check_name(db, user, body.name, body.parent_id, None)
    folder = Folder(user_id=user.id, name=body.name, parent_id=body.parent_id)
    db.add(folder)
    db.commit()
    return _out(db, user, folder, subfolders=0)


@router.get("/{folder_id}")
def get_folder(folder_id: int, user: CurrentUser, db: DbSession) -> FolderDetail:
    folder = _get(db, user, folder_id)
    children = _children(db, user)
    detail = FolderDetail.model_validate(
        _out(db, user, folder, subfolders=children[folder.id]).model_dump()
    )
    detail.path = [FolderCrumb(id=f.id, name=f.name) for f in _path(db, folder)]
    subfolders = db.scalars(
        select(Folder).where(Folder.parent_id == folder.id).order_by(func.lower(Folder.name))
    )
    detail.folders = [_out(db, user, f, subfolders=children[f.id]) for f in subfolders]
    detail.videos = video_summaries(db, user.id, _videos(db, user, folder.id))
    return detail


@router.patch("/{folder_id}")
def update_folder(
    folder_id: int, body: FolderUpdate, user: CurrentUser, db: DbSession
) -> FolderOut:
    folder = _get(db, user, folder_id)
    parent_id = body.parent_id if "parent_id" in body.model_fields_set else folder.parent_id
    if parent_id != folder.parent_id:
        _check_parent(db, user, parent_id, folder)
    name = body.name or folder.name
    _check_name(db, user, name, parent_id, folder.id)
    folder.name, folder.parent_id = name, parent_id
    db.commit()
    return _out(db, user, folder, subfolders=_children(db, user)[folder.id])


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: int, user: CurrentUser, db: DbSession) -> None:
    """The folder and the folders inside it go; the videos stay in the library."""
    db.delete(_get(db, user, folder_id))
    db.commit()


@router.put("/{folder_id}/videos/{video_id}")
def add_video(folder_id: int, video_id: int, user: CurrentUser, db: DbSession) -> FolderOut:
    folder = _get(db, user, folder_id)
    ensure_visible(user, db.get(Video, video_id))
    exists = db.scalar(
        select(FolderItem.id).where(
            FolderItem.folder_id == folder.id, FolderItem.video_id == video_id
        )
    )
    if exists is None:
        db.add(FolderItem(folder_id=folder.id, video_id=video_id))
        db.commit()
    return _out(db, user, folder, subfolders=_children(db, user)[folder.id], video_id=video_id)


@router.delete("/{folder_id}/videos/{video_id}")
def remove_video(folder_id: int, video_id: int, user: CurrentUser, db: DbSession) -> FolderOut:
    folder = _get(db, user, folder_id)
    item = db.scalar(
        select(FolderItem).where(FolderItem.folder_id == folder.id, FolderItem.video_id == video_id)
    )
    if item is not None:
        db.delete(item)
        db.commit()
    return _out(db, user, folder, subfolders=_children(db, user)[folder.id], video_id=video_id)
