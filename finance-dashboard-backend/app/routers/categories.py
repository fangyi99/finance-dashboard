import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Category,
    CategoryFeedback,
    MerchantCategoryMap,
    RecurringRule,
    Transaction,
    User,
)

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    user_id: uuid.UUID
    name: str = Field(min_length=1, max_length=50)
    parent_category_id: Optional[uuid.UUID] = None
    # Ignored when a parent is given: subcategories inherit the parent's type.
    type: Literal["income", "expense", "transfer"] = "expense"


class CategoryUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class CategoryOut(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID]
    name: str
    parent_category_id: Optional[uuid.UUID]
    type: str
    is_system_default: bool

    class Config:
        from_attributes = True


def _visible_to(user_id: uuid.UUID):
    """System defaults (user_id NULL) plus this user's own categories."""
    return or_(Category.user_id.is_(None), Category.user_id == user_id)


def _name_taken(db, user_id, name, parent_id, exclude_id=None) -> bool:
    query = db.query(Category).filter(
        _visible_to(user_id),
        func.lower(Category.name) == name.lower(),
        Category.parent_category_id == parent_id,
    )
    if exclude_id:
        query = query.filter(Category.id != exclude_id)
    return query.first() is not None


def _get_owned_category(db, category_id, user_id) -> Category:
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.user_id != user_id:  # covers system defaults and other users' categories
        raise HTTPException(status_code=403, detail="You can only change your own categories")
    return category


@router.get("/{user_id}", response_model=List[CategoryOut])
def list_categories(user_id: uuid.UUID, db: Session = Depends(get_db)):
    # Flat list; the client builds the tree from parent_category_id.
    return db.query(Category).filter(_visible_to(user_id)).order_by(Category.name).all()


@router.post("", response_model=CategoryOut)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name can't be blank")

    category_type = payload.type
    if payload.parent_category_id:
        parent = db.get(Category, payload.parent_category_id)
        if not parent or parent.user_id not in (None, payload.user_id):
            raise HTTPException(status_code=404, detail="Parent category not found")
        if parent.parent_category_id is not None:
            raise HTTPException(status_code=400, detail="Subcategories can only be one level deep")
        category_type = parent.type

    if _name_taken(db, payload.user_id, name, payload.parent_category_id):
        raise HTTPException(status_code=409, detail="A category with that name already exists here")

    category = Category(
        user_id=payload.user_id,
        name=name,
        parent_category_id=payload.parent_category_id,
        type=category_type,
        is_system_default=False,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryOut)
def rename_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    category = _get_owned_category(db, category_id, user_id)

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name can't be blank")
    if _name_taken(db, user_id, name, category.parent_category_id, exclude_id=category.id):
        raise HTTPException(status_code=409, detail="A category with that name already exists here")

    category.name = name
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: uuid.UUID, user_id: uuid.UUID, db: Session = Depends(get_db)
):
    category = _get_owned_category(db, category_id, user_id)

    if db.query(Category).filter(Category.parent_category_id == category_id).first():
        raise HTTPException(status_code=400, detail="Delete or move its subcategories first")

    uncategorized = (
        db.query(Category)
        .filter(Category.name == "Uncategorized", Category.user_id.is_(None))
        .first()
    )
    if not uncategorized:
        raise HTTPException(
            status_code=500, detail="'Uncategorized' is missing, run the seed script"
        )

    # Anything pointing at this category falls back to Uncategorized.
    db.query(Transaction).filter(Transaction.category_id == category_id).update(
        {"category_id": uncategorized.id, "category_confidence": None, "category_source": "rule"}
    )
    db.query(RecurringRule).filter(RecurringRule.category_id == category_id).update(
        {"category_id": uncategorized.id}
    )
    # Mappings and feedback rows for a deleted category have nothing left to teach.
    db.query(MerchantCategoryMap).filter(MerchantCategoryMap.category_id == category_id).delete()
    db.query(CategoryFeedback).filter(
        CategoryFeedback.corrected_category_id == category_id
    ).delete()

    db.delete(category)
    db.commit()
    return Response(status_code=204)