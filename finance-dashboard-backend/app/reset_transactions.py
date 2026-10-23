"""
Clears what your statements put in the database, so you can re-import from scratch. DESTRUCTIVE, so it shows you
exactly what it will delete and makes you type DELETE before it does anything.

    python -m app.reset_transactions                       the transactions, and the corrections attached to them
    python -m app.reset_transactions --account <uuid>      just one account (safer: keeps Stripe's, say)

  and any of these, to go further:
    --reset-balances    clear each account's stored balance, its date and its last-sync time. (The balance is NOT
                        worked out from transactions: it's copied from the statement when you import, so deleting
                        transactions alone leaves it showing.)
    --and-rules         the categorisation rules you taught the app
    --and-recurring     your recurring rules (their names come from statement text)
    --and-learned       merchant mappings learned from your corrections
    --and-accounts      the accounts THEMSELVES (you'll add them again in the app)
    --privacy           everything derived from your statements: transactions, corrections, taught rules, recurring
                        rules, learned merchants and balances. Your accounts stay, empty.
    --include-sandbox   also clear the sandbox's data (by default it's left alone: its Reset button rebuilds it)

    For a clean slate:   python -m app.reset_transactions --privacy --and-accounts

What always goes: the transactions, and the category-correction history attached to them (that history points AT the
transactions, so it can't survive without them; a plain DELETE FROM transactions fails if you've ever corrected a
category). What is kept unless you ask: accounts (and the import method each is locked to), categories and budgets,
and the things listed above.

Why you need this to re-import: importing is idempotent (re-uploading the same statement adds nothing), and a REDACTED
copy of a statement reads differently, so it would not match the old rows and would sit beside them as duplicates.
Clear first, then upload.

Everything happens in ONE database transaction: if anything fails, nothing is deleted.
"""

import sys

from .database import SessionLocal
from .demo.seed import DEMO_USER_ID
from .models import Account, CategorisationRule, CategoryFeedback, MerchantCategoryMap, RecurringRule, Transaction

EMPTY = {"transactions": 0, "corrections": 0, "rules": 0, "recurring": 0, "learned": 0, "balances": 0, "accounts": 0}


def plan(db, account_id=None, include_sandbox=False):
    """What would be touched: one row per account, with how many transactions and corrections."""
    query = db.query(Account)
    if account_id:
        query = query.filter(Account.id == account_id)  # named explicitly: allowed, even if it's a sandbox account
    elif not include_sandbox:
        query = query.filter(Account.user_id != DEMO_USER_ID)
    rows = []
    for account in query.order_by(Account.created_at).all():
        tx = db.query(Transaction).filter(Transaction.account_id == account.id)
        feedback = (
            db.query(CategoryFeedback)
            .join(Transaction, CategoryFeedback.transaction_id == Transaction.id)
            .filter(Transaction.account_id == account.id)
        )
        rows.append(
            {
                "account": account,
                "label": account.display_name or account.institution_name or str(account.id)[:8],
                "transactions": tx.count(),
                "corrections": feedback.count(),
            }
        )
    return rows


def reset(db, account_id=None, reset_balances=False, and_rules=False, and_recurring=False, and_learned=False,
          and_accounts=False, include_sandbox=False):
    """Does the deletion (without committing). Returns the counts it changed."""
    accounts = plan(db, account_id, include_sandbox)
    ids = [r["account"].id for r in accounts]
    if not ids:
        return dict(EMPTY)
    tx_ids = db.query(Transaction.id).filter(Transaction.account_id.in_(ids))
    # 1. the correction history points AT transactions, so it goes first
    corrections = (
        db.query(CategoryFeedback).filter(CategoryFeedback.transaction_id.in_(tx_ids)).delete(synchronize_session=False)
    )
    # 2. the transactions (a pairing link into another account is cleared by the database itself)
    transactions = db.query(Transaction).filter(Transaction.account_id.in_(ids)).delete(synchronize_session=False)
    user_ids = {r["account"].user_id for r in accounts}
    rules = recurring = learned = balances = deleted_accounts = 0
    if and_rules:
        rules = db.query(CategorisationRule).filter(CategorisationRule.user_id.in_(user_ids)).delete(synchronize_session=False)
    if and_recurring:
        recurring = db.query(RecurringRule).filter(RecurringRule.user_id.in_(user_ids)).delete(synchronize_session=False)
    if and_learned:  # the shared table: only what was LEARNED from corrections, never the built-in merchant list
        learned = db.query(MerchantCategoryMap).filter(MerchantCategoryMap.source != "seed_data").delete(synchronize_session=False)
    if and_accounts:
        # (a recurring rule that pointed at an account just loses that link; the database does it)
        deleted_accounts = db.query(Account).filter(Account.id.in_(ids)).delete(synchronize_session=False)
    elif reset_balances:
        balances = db.query(Account).filter(Account.id.in_(ids)).update(
            {"balance": None, "balance_as_of": None, "last_synced_at": None}, synchronize_session=False
        )
    return {"transactions": transactions, "corrections": corrections, "rules": rules, "recurring": recurring,
            "learned": learned, "balances": balances, "accounts": deleted_accounts}


def main(argv):
    account_id = argv[argv.index("--account") + 1] if "--account" in argv else None
    privacy = "--privacy" in argv
    options = {
        "reset_balances": privacy or "--reset-balances" in argv,
        "and_rules": privacy or "--and-rules" in argv,
        "and_recurring": privacy or "--and-recurring" in argv,
        "and_learned": privacy or "--and-learned" in argv,
        "and_accounts": "--and-accounts" in argv,
        "include_sandbox": "--include-sandbox" in argv,
    }
    db = SessionLocal()
    try:
        rows = plan(db, account_id, options["include_sandbox"])
        sandbox_accounts = db.query(Account).filter(Account.user_id == DEMO_USER_ID).count()
        if not rows:
            if account_id:
                raise SystemExit("No matching account found.")
            hint = " The sandbox's accounts are left alone (use --include-sandbox to clear them)." if sandbox_accounts and not options["include_sandbox"] else ""
            raise SystemExit("There are no accounts to clear." + hint)
        total = sum(r["transactions"] for r in rows)
        print("This will DELETE:")
        for r in rows:
            print(f"   {r['label']:<24} {r['transactions']:>6} transactions, {r['corrections']:>4} category corrections   ({r['account'].source or 'no import method yet'})")
            print(f"   {'':<24} id: {r['account'].id}   balance: {r['account'].balance if r['account'].balance is not None else '-'}")
        print(f"   {'TOTAL':<24} {total:>6} transactions")
        also = [text for flag, text in (
            ("and_rules", "your taught rules"), ("and_recurring", "your recurring rules"),
            ("and_learned", "learned merchant mappings"),
        ) if options[flag]]
        if options["and_accounts"]:
            also.append("THE ACCOUNTS THEMSELVES")
        elif options["reset_balances"]:
            also.append("each account's stored balance")
        print("It will ALSO delete: " + ", ".join(also) + "." if also else "It will leave every account, with its balance, exactly as it is.")
        kept = [] if options["and_accounts"] else ["your accounts"]
        kept += ["categories", "budgets"]
        print("It will KEEP: " + ", ".join(kept) + ".")
        if not options["include_sandbox"] and not account_id and sandbox_accounts:
            print("(The sandbox's data is left alone: its Reset button rebuilds it. Use --include-sandbox to clear it too.)")
        if total == 0 and not also:
            raise SystemExit("Nothing to delete.")
        if input("\nThis cannot be undone. Type DELETE to continue: ").strip() != "DELETE":
            raise SystemExit("Cancelled. Nothing was deleted.")
        done = reset(db, account_id, **options)
        db.commit()
        extras = [f"{done[k]} {label}" for k, label in (
            ("rules", "taught rules"), ("recurring", "recurring rules"), ("learned", "learned merchant mappings"),
            ("balances", "balances cleared"), ("accounts", "accounts"),
        ) if done[k]]
        print(f"Deleted {done['transactions']} transactions and {done['corrections']} corrections" + (", and " + ", ".join(extras) if extras else "") + ".")
    except SystemExit:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])