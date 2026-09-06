from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.domains.tree import schemas
from app.domains.tree import service as tree_service
from app.domains.tree.contracts import TreeAuthor, TreeReferences
from app.domains.tree.dependencies import get_current_user, get_db, get_tree_references


router = APIRouter(prefix="/tree", tags=["tree"])


@router.get("/posts", response_model=schemas.TreeFeedPage)
def list_tree_posts(
    category: str = Query(default="notice", max_length=20),
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    references: TreeReferences = Depends(get_tree_references),
    db: Session = Depends(get_db),
) -> schemas.TreeFeedPage:
    try:
        return tree_service.list_posts(
            db,
            category=category,
            query=q,
            limit=limit,
            cursor=cursor,
            references=references,
        )
    except tree_service.TreeCategoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown tree category",
        ) from exc


@router.post(
    "/posts", response_model=schemas.TreePostDetail, status_code=status.HTTP_201_CREATED
)
def create_tree_post(
    data: schemas.TreePostCreate,
    references: TreeReferences = Depends(get_tree_references),
    db: Session = Depends(get_db),
    user: TreeAuthor = Depends(get_current_user),
) -> schemas.TreePostDetail:
    try:
        return tree_service.create_post(db, user, data, references=references)
    except tree_service.TreeNoticeWriteForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except tree_service.TreeRelatedCharacterError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Related character not found"
        ) from exc


@router.get("/posts/{post_id}", response_model=schemas.TreePostDetail)
def get_tree_post(
    post_id: str, db: Session = Depends(get_db)
) -> schemas.TreePostDetail:
    try:
        return tree_service.get_post(db, post_id)
    except tree_service.TreePostNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tree post not found"
        ) from exc


@router.post("/posts/{post_id}/comments", response_model=schemas.TreePostDetail)
def create_tree_comment(
    post_id: str,
    data: schemas.TreeCommentCreate,
    db: Session = Depends(get_db),
    user: TreeAuthor = Depends(get_current_user),
) -> schemas.TreePostDetail:
    try:
        return tree_service.create_comment(db, user, post_id, data)
    except tree_service.TreePostNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tree post not found"
        ) from exc
