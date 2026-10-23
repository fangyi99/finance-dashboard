"""
The review queue's endpoints. See app/review.py for what "needs review" means and why transactions are grouped.

    GET  /review/{user_id}            the groups to review, biggest spend first, with suggestions and quick choices
         ?skipped=true                ...or the groups you skipped, so you can come back to them
    GET  /review/{user_id}/summary    just the numbers for the dashboard prompt
    POST /review/resolve              file a whole group under one category (optionally teaching a rule)
    POST /review/skip                 "I don't know": take a group out of the queue
    POST /review/unskip               move a skipped group back

A group is addressed by its `key`, and its members are looked up again when you act, so a payment that arrived
after the list was loaded is included, and a group that was already dealt with answers 404.
"""

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..review import ReviewError, load_review, resolve_group, skip_group, unskip_group

router = APIRouter(prefix="/review", tags=["review"])


class NewCategory(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: Optional[Literal["income", "expense", "transfer"]] = None  # default: by direction of the money


class ResolveBody(BaseModel):
    user_id: uuid.UUID
    group_key: str = Field(min_length=1)
    category_id: Optional[uuid.UUID] = None
    new_category: Optional[NewCategory] = None
    apply_to_all: bool = True

    @model_validator(mode="after")
    def exactly_one_category(self):
        if (self.category_id is None) == (self.new_category is None):
            raise ValueError("Give either category_id or new_category, not both and not neither.")
        return self


class GroupBody(BaseModel):
    user_id: uuid.UUID
    group_key: str = Field(min_length=1)


def _user(db: Session, user_id: uuid.UUID) -> None:
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")


def _guard(call):
    try:
        return call()
    except ReviewError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.get("/{user_id}")
def get_review(user_id: uuid.UUID, skipped: bool = False, db: Session = Depends(get_db)):
    _user(db, user_id)
    return load_review(db, user_id, skipped=skipped)


@router.get("/{user_id}/summary")
def get_summary(user_id: uuid.UUID, db: Session = Depends(get_db)):
    _user(db, user_id)
    return load_review(db, user_id)["summary"]


@router.post("/resolve")
def resolve(body: ResolveBody, db: Session = Depends(get_db)):
    _user(db, body.user_id)
    new = body.new_category.model_dump() if body.new_category else None
    result = _guard(lambda: resolve_group(db, body.user_id, body.group_key, body.category_id, new, body.apply_to_all))
    return {**result, "summary": load_review(db, body.user_id)["summary"]}


@router.post("/skip")
def skip(body: GroupBody, db: Session = Depends(get_db)):
    _user(db, body.user_id)
    skipped = _guard(lambda: skip_group(db, body.user_id, body.group_key))
    return {"skipped": skipped, "summary": load_review(db, body.user_id)["summary"]}


@router.post("/unskip")
def unskip(body: GroupBody, db: Session = Depends(get_db)):
    _user(db, body.user_id)
    restored = _guard(lambda: unskip_group(db, body.user_id, body.group_key))
    return {"restored": restored, "summary": load_review(db, body.user_id)["summary"]}