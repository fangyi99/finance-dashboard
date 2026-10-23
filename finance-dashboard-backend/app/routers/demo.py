"""
Sandbox mode endpoints. The app calls POST /demo/start when the user switches sandbox mode on; it gets back
the demo user's id and uses that instead of its normal one. Everything else (accounts, budgets, the dashboard)
then works unchanged, because the demo is just another user.

    GET  /demo          is the sandbox set up, and how fresh is it?   (changes nothing)
    POST /demo/start    make sure it exists and isn't stale; refreshes it only if it needs to
    POST /demo/reset    put the sandbox back to its original state (throws away changes made in it)

None of these can touch anyone else's data: they only ever read or delete the one demo user's rows.

If setting up fails, the two likely causes get a plain explanation (it's shown in the app's alert) instead of a
bare "Internal Server Error": the standard categories aren't seeded, or the categorisation migration hasn't been
applied. A failed set-up rolls back, so an existing sandbox is left as it was.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from ..database import get_db
from ..demo.seed import ensure_demo, reset_demo, status

router = APIRouter(prefix="/demo", tags=["demo"])


def _explain(error: Exception):
    """A plain-English reason for the setup mistakes we can recognise, or None."""
    if isinstance(error, KeyError):  # the seed looks categories up by name
        return "The sandbox needs the standard categories first. Run `python -m app.seed`, then try again."
    if isinstance(error, ProgrammingError):  # a column or table the code expects isn't in the database
        return "The database is missing the categorisation migration. Run `python -m alembic upgrade head`, then try again."
    return None


def _guarded(db: Session, work):
    try:
        return work()
    except Exception as error:
        db.rollback()
        reason = _explain(error)
        if reason is None:
            raise
        raise HTTPException(status_code=500, detail=reason)


@router.get("")
def demo_status(db: Session = Depends(get_db)):
    return status(db)


@router.post("/start")
def demo_start(db: Session = Depends(get_db)):
    current, refreshed = _guarded(db, lambda: ensure_demo(db))
    return {**current, "refreshed": refreshed}


@router.post("/reset")
def demo_reset(db: Session = Depends(get_db)):
    return {**_guarded(db, lambda: reset_demo(db)), "refreshed": True}