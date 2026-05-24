from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_password_hash
from ..database import get_db
from ..deps import get_admin_user, get_current_user
from ..models import Flashcard, Test, User, ViewHistory
from ..schemas import UserOut, UserUpdate, ViewHistoryOut

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.username:
        candidate = payload.username.strip()
        existing = db.query(User).filter(User.username == candidate, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already in use")
        current_user.username = candidate

    if payload.email:
        candidate = payload.email.strip().lower()
        existing = db.query(User).filter(User.email == candidate, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = candidate

    if payload.password:
        current_user.hashed_password = get_password_hash(payload.password)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    return db.query(User).order_by(User.id.asc()).all()


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.username:
        candidate = payload.username.strip()
        existing = db.query(User).filter(User.username == candidate, User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already in use")
        user.username = candidate

    if payload.email:
        candidate = payload.email.strip().lower()
        existing = db.query(User).filter(User.email == candidate, User.id != user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = candidate

    if payload.password:
        user.hashed_password = get_password_hash(payload.password)

    if payload.role in {"admin", "user"}:
        user.role = payload.role

    if user.id == admin_user.id and user.role != "admin":
        raise HTTPException(status_code=400, detail="You cannot remove your own admin role")

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    flashcard_ids = [
        card_id
        for (card_id,) in db.query(Flashcard.id).filter(Flashcard.user_id == user_id).all()
    ]
    if flashcard_ids:
        (
            db.query(ViewHistory)
            .filter(ViewHistory.flashcard_id.in_(flashcard_ids))
            .delete(synchronize_session=False)
        )
    db.query(ViewHistory).filter(ViewHistory.user_id == user_id).delete(synchronize_session=False)
    db.query(Flashcard).filter(Flashcard.user_id == user_id).delete(synchronize_session=False)
    db.query(Test).filter(Test.user_id == user_id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    return {"message": "User deleted"}


@router.get("/{user_id}/history", response_model=list[ViewHistoryOut])
def user_history(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    items = db.query(ViewHistory).filter(ViewHistory.user_id == user_id).order_by(ViewHistory.id.desc()).all()
    return [
        ViewHistoryOut(
            id=item.id,
            user_id=item.user_id,
            flashcard_id=item.flashcard_id,
            notes=item.notes,
            was_correct=item.was_correct,
            viewed_at=item.viewed_at,
            flashcard_question=item.flashcard.question if item.flashcard else None,
            flashcard_test=item.flashcard.category if item.flashcard else None,
            username=item.user.username if item.user else None,
        )
        for item in items
    ]
