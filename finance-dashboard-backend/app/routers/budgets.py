import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Account, Budget, Category, Transaction, User

router = APIRouter(prefix="/budgets", tags=["budgets"])

MAX_AMOUNT = Decimal("9999999999.99")  # the largest that fits Numeric(12, 2)
CENT = Decimal("0.01")


class BudgetCreate(BaseModel):
    user_id: uuid.UUID
    # Checked in the endpoint rather than with min_length, so a name of only spaces gets the
    # same plain-English message as an empty one.
    name: str = Field(max_length=60)
    amount: Decimal = Field(gt=0, le=MAX_AMOUNT, decimal_places=2)
    # What it measures: a category (and everything under it), or none for all spending.
    category_id: Optional[uuid.UUID] = None


class BudgetUpdate(BaseModel):
    # Leaving a field out leaves it alone. category_id is the one that can be cleared:
    # send it as null to go back to all spending.
    name: Optional[str] = Field(default=None, max_length=60)
    amount: Optional[Decimal] = Field(default=None, gt=0, le=MAX_AMOUNT, decimal_places=2)
    category_id: Optional[uuid.UUID] = None


class BudgetOut(BaseModel):
    id: uuid.UUID
    name: str
    amount: Decimal
    category_id: Optional[uuid.UUID]
    category_name: Optional[str]
    spent: Decimal  # so far this month
    remaining: Decimal  # amount - spent; negative once it's been exceeded
    month: str  # "2026-10": the month `spent` is for


# ---- what counts as spending ---------------------------------------------------------------


def _is_uncategorized(category: Category) -> bool:
    # The built-in "Uncategorized" category: where a transaction sits until it's been sorted.
    return category.name == "Uncategorized" and category.user_id is None and not category.parent_category_id


def _expense_value(amount: Decimal, category_type: str) -> Decimal:
    """
    How much of one CATEGORISED transaction counts as spending. Anything filed under an
    expense category counts at its full size (the way Cash Flow counts it), anything filed
    under a transfer category counts only if the money went out, and income never counts.

    Transactions with no category, or still in "Uncategorized", don't reach this function:
    only spending that has been sorted into a real category counts towards a budget.
    """
    if category_type == "expense":
        return abs(amount)
    if category_type == "transfer":
        return -amount if amount < 0 else Decimal(0)
    return Decimal(0)  # income


def _month_bounds(year: Optional[int], month: Optional[int]):
    today = date.today()
    year = year or today.year
    month = month or today.month
    return year, month, date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _budget_outs(
    db: Session, user_id: uuid.UUID, budgets: List[Budget], year: Optional[int], month: Optional[int]
) -> List[BudgetOut]:
    year, month, start, end = _month_bounds(year, month)

    categories = {c.id: c for c in db.query(Category).all()}
    uncategorized = {c.id for c in categories.values() if _is_uncategorized(c)}

    # One query for the month's spending, then each budget is a sum over it. Only
    # transactions with a real category are kept: no category, or "Uncategorized", means it
    # hasn't been sorted yet, so it doesn't count until it is.
    rows = (
        db.query(Transaction.category_id, Transaction.amount, Category.type)
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .join(Category, Transaction.category_id == Category.id)
        .filter(Account.user_id == user_id, Transaction.transaction_date.between(start, end))
        .all()
    )
    spending = [
        (category_id, _expense_value(amount, category_type))
        for category_id, amount, category_type in rows
        if category_id not in uncategorized
    ]

    children = {}
    for category in categories.values():
        if category.parent_category_id:
            children.setdefault(category.parent_category_id, []).append(category.id)

    def family(category_id: uuid.UUID) -> set:
        # The category and everything under it, so "Food" covers Groceries, Dining...
        found, pending = {category_id}, [category_id]
        while pending:
            for child in children.get(pending.pop(), []):
                if child not in found:
                    found.add(child)
                    pending.append(child)
        return found

    outs = []
    for budget in budgets:
        if budget.category_id is None:
            spent = sum((value for _, value in spending), Decimal(0))
        else:
            ids = family(budget.category_id)
            spent = sum((value for category_id, value in spending if category_id in ids), Decimal(0))
        spent = spent.quantize(CENT)
        category = categories.get(budget.category_id) if budget.category_id else None
        outs.append(
            BudgetOut(
                id=budget.id,
                name=budget.name,
                amount=budget.amount,
                category_id=budget.category_id,
                category_name=category.name if category else None,
                spent=spent,
                remaining=(budget.amount - spent).quantize(CENT),
                month=f"{year}-{month:02d}",
            )
        )
    return outs


# ---- validation ----------------------------------------------------------------------------


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Add a budget name.")
    return cleaned


def _check_category(db: Session, category_id: uuid.UUID, user_id: uuid.UUID) -> None:
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.user_id not in (None, user_id):
        raise HTTPException(status_code=403, detail="That category isn't available to you")
    if category.type != "expense":
        raise HTTPException(status_code=422, detail="Budgets track spending, so pick an expense category.")
    if _is_uncategorized(category):
        # Uncategorized spending never counts towards a budget, so it would always read $0.
        raise HTTPException(
            status_code=422,
            detail="Uncategorized spending doesn't count towards budgets, so pick a category.",
        )


def _get_budget(db: Session, budget_id: uuid.UUID) -> Budget:
    budget = db.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


# ---- endpoints -----------------------------------------------------------------------------

YearParam = Query(None, ge=2000, le=2100)
MonthParam = Query(None, ge=1, le=12)


@router.get("/by-id/{budget_id}", response_model=BudgetOut)
def get_budget(
    budget_id: uuid.UUID,
    year: Optional[int] = YearParam,
    month: Optional[int] = MonthParam,
    db: Session = Depends(get_db),
):
    budget = _get_budget(db, budget_id)
    return _budget_outs(db, budget.user_id, [budget], year, month)[0]


@router.get("/{user_id}", response_model=List[BudgetOut])
def list_budgets(
    user_id: uuid.UUID,
    year: Optional[int] = YearParam,
    month: Optional[int] = MonthParam,
    db: Session = Depends(get_db),
):
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user_id)
        .order_by(Budget.created_at, Budget.name)
        .all()
    )
    return _budget_outs(db, user_id, budgets, year, month)


@router.post("", response_model=BudgetOut, status_code=201)
def create_budget(payload: BudgetCreate, db: Session = Depends(get_db)):
    name = _clean_name(payload.name)
    if not db.get(User, payload.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if payload.category_id:
        _check_category(db, payload.category_id, payload.user_id)

    budget = Budget(
        user_id=payload.user_id, name=name, amount=payload.amount, category_id=payload.category_id
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return _budget_outs(db, budget.user_id, [budget], None, None)[0]


@router.patch("/{budget_id}", response_model=BudgetOut)
def update_budget(budget_id: uuid.UUID, payload: BudgetUpdate, db: Session = Depends(get_db)):
    budget = _get_budget(db, budget_id)
    data = payload.model_dump(exclude_unset=True)

    # Check everything first, so a request with one bad part changes nothing at all.
    name = _clean_name(data["name"]) if data.get("name") is not None else None
    if data.get("category_id") is not None:
        _check_category(db, data["category_id"], budget.user_id)

    if name is not None:
        budget.name = name
    if data.get("amount") is not None:
        budget.amount = data["amount"]
    if "category_id" in data:
        budget.category_id = data["category_id"]
    db.commit()
    db.refresh(budget)
    return _budget_outs(db, budget.user_id, [budget], None, None)[0]


@router.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: uuid.UUID, db: Session = Depends(get_db)):
    budget = _get_budget(db, budget_id)
    db.delete(budget)
    db.commit()
    return Response(status_code=204)