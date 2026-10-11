"""
Recurring-transaction detection and scheduling.

Detection looks through a user's recent transactions for charges (or credits) that repeat
at a regular interval, and proposes them as *suggestions* — nothing is created until the
user approves it. A suggestion becomes a row in recurring_rules; the Upcoming widget then
reads those rules.

What counts as "the same charge": transactions whose descriptions boil down to the same
key (see description_key) and have the same sign. What counts as "recurring":

  - at least MIN_OCCURRENCES of them in the lookback window,
  - spaced regularly enough to be weekly, every two weeks, or monthly, and
  - either a fixed amount (within 5% of the latest — so a price rise is handled), or, for
    monthly charges only, a variable amount (a utility bill that moves around).

Deliberately NOT detected:
  - yearly charges (three years of history would be needed; add those by hand),
  - wallet top-ups ("TOP-UP TO PAYLAH"): they repeat but aren't scheduled charges,
  - variable weekly/fortnightly amounts: that's a spending habit (groceries, coffee), not
    a scheduled charge.
"""

import calendar
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from statistics import median
from typing import Iterable, NamedTuple, Optional

from .categorization import normalize_description

MIN_OCCURRENCES = 3
LOOKBACK_DAYS = 400  # a little over a year of history
FIXED_TOLERANCE = Decimal("0.05")  # "same amount" means within 5% of the latest
VARIABLE_MAX_DEVIATION = Decimal("0.35")  # a monthly bill may swing up to 35% around its median
MAX_KEY_TOKENS = 8

# How far apart (in days) consecutive occurrences may be, per frequency.
GAP_WINDOWS = {"weekly": (6, 8), "biweekly": (12, 16), "monthly": (26, 35)}
REGULARITY = Decimal("0.75")  # at least this share of the gaps must fall inside the window

TOPUP_RE = re.compile(r"\bTOP[- ]?UP\s+TO\b")

# Generic bank wording at the start of a description, dropped when making a readable label.
GENERIC_LABEL_PREFIXES = [
    "DEBIT CARD TRANSACTION",
    "FAST PAYMENT RECEIPT",
    "PAYNOW TRANSFER",
    "FUNDS TRANSFER",
    "BILL PAYMENT",
    "GIRO PAYMENT",
    "INTERNET BANKING",
]


def description_key(description: str) -> str:
    """
    A stable fingerprint for "the same charge" across months. Reference numbers, card
    numbers and dates are what differ from one month to the next, so any word containing a
    digit is dropped (after the cleaner has already removed long digit runs), leaving the
    merchant or payee wording.
    """
    return _key_from_normalized(normalize_description(description))


def _key_from_normalized(normalized: str) -> str:
    tokens = []
    for token in normalized.split():
        if any(ch.isdigit() for ch in token) or not any(ch.isalpha() for ch in token):
            continue
        token = token.strip(":*!,;")
        if token:
            tokens.append(token)
    return " ".join(tokens[:MAX_KEY_TOKENS])


def suggest_label(key: str) -> str:
    label = key
    for prefix in GENERIC_LABEL_PREFIXES:
        if label.startswith(prefix + " "):
            label = label[len(prefix) + 1 :]
            break
    return (label.strip() or key).title()[:40]


# ---- dates ---------------------------------------------------------------------------


class Interval(NamedTuple):
    """How often something repeats: "every 3 months" is Interval(3, "month")."""

    count: int
    unit: str  # 'day' | 'week' | 'month' | 'year'


UNITS = ("day", "week", "month", "year")

# The named frequencies the detector and the "make this recurring" checkbox still speak.
PRESET_INTERVALS = {
    "weekly": Interval(1, "week"),
    "biweekly": Interval(2, "week"),
    "monthly": Interval(1, "month"),
    "yearly": Interval(1, "year"),
}


def as_interval(value) -> Interval:
    """A preset name ('monthly'), an (count, unit) pair, or an Interval -> an Interval."""
    if isinstance(value, str):
        return Interval(1, "day") if value == "daily" else PRESET_INTERVALS[value]
    count, unit = value
    return Interval(int(count), unit)


def frequency_label(count: int, unit: str) -> str:
    """The readable name stored beside the interval: 'weekly', 'daily'... or 'custom'."""
    named = {**PRESET_INTERVALS, "daily": Interval(1, "day")}
    for name, interval in named.items():
        if (count, unit) == tuple(interval):
            return name
    return "custom"


def add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year = d.year + index // 12
    month = index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def advance(d: date, interval, steps: int = 1) -> date:
    # Always measured from the original date (not step by step), so a charge on the 31st
    # returns to the 31st after a short month instead of drifting to the 28th for good.
    count, unit = as_interval(interval)
    n = count * steps
    if unit == "day":
        return d + timedelta(days=n)
    if unit == "week":
        return d + timedelta(weeks=n)
    if unit == "month":
        return add_months(d, n)
    if unit == "year":
        return add_months(d, 12 * n)
    raise ValueError(f"unknown unit {unit!r}")


def _steps_to_reach(anchor: date, interval, today: date, first_step: int) -> int:
    """The fewest steps (at least first_step) after which the series reaches today or later."""
    iv = as_interval(interval)
    if iv.unit in ("day", "week"):
        period = iv.count * (1 if iv.unit == "day" else 7)
        steps = -(-(today - anchor).days // period)  # ceiling division
    else:
        months_per_step = iv.count * (1 if iv.unit == "month" else 12)
        steps = ((today.year - anchor.year) * 12 + (today.month - anchor.month)) // months_per_step
    steps = max(first_step, steps)
    # Month lengths vary, so that estimate can be a step off either way; settle it exactly.
    while steps > first_step and advance(anchor, iv, steps - 1) >= today:
        steps -= 1
    while advance(anchor, iv, steps) < today:
        steps += 1
    return steps


def next_due_on_or_after(last: date, interval, today: date) -> date:
    """`last` is a PAST OCCURRENCE: the next one is a step later, rolled forward to today or after."""
    iv = as_interval(interval)
    return advance(last, iv, _steps_to_reach(last, iv, today, 1))


def next_on_or_after_anchor(anchor: date, interval, today: date) -> date:
    """
    The first date in a series that STARTS at `anchor` and is today or later — the anchor
    itself counts. This is for a date typed in by hand ("it starts on 1 Nov"), which is the
    first occurrence, unlike next_due_on_or_after where the date is a past occurrence and
    the next one is a full step later.
    """
    iv = as_interval(interval)
    return advance(anchor, iv, _steps_to_reach(anchor, iv, today, 0))


# ---- detection -----------------------------------------------------------------------


@dataclass
class Candidate:
    pattern: str
    label: str
    frequency: str
    expected_amount: Decimal  # signed: negative for a charge, positive for a credit
    tolerance: Decimal
    amount_varies: bool
    occurrences: int
    first_date: date
    last_date: date
    next_due_date: date
    category_id: Optional[object]
    currency: str
    sample_description: str
    account_id: Optional[object] = None

    def to_dict(self, category_names: Optional[dict] = None) -> dict:
        return {
            "pattern": self.pattern,
            "label": self.label,
            "frequency": self.frequency,
            "interval_count": PRESET_INTERVALS[self.frequency].count,
            "interval_unit": PRESET_INTERVALS[self.frequency].unit,
            "expected_amount": str(self.expected_amount),
            "currency": self.currency,
            "amount_tolerance_pct": str(self.tolerance),
            "amount_varies": self.amount_varies,
            "occurrences": self.occurrences,
            "first_date": self.first_date.isoformat(),
            "last_date": self.last_date.isoformat(),
            "next_due_date": self.next_due_date.isoformat(),
            "account_id": str(self.account_id) if self.account_id else None,
            "category_id": str(self.category_id) if self.category_id else None,
            "category_name": (category_names or {}).get(self.category_id) if self.category_id else None,
            "sample_description": self.sample_description[:80],
        }


def _cents(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def classify_frequency(dates: list, allow=("weekly", "biweekly", "monthly")) -> Optional[str]:
    if len(dates) < MIN_OCCURRENCES:
        return None
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    typical = median(gaps)
    for name in allow:
        low, high = GAP_WINDOWS[name]
        if low <= typical <= high:
            inside = sum(1 for g in gaps if low <= g <= high)
            if Decimal(inside) / Decimal(len(gaps)) >= REGULARITY:
                return name
    return None


def _latest_fixed_run(rows: list) -> list:
    """The most recent occurrences that all share (about) the latest amount."""
    latest = rows[-1].amount
    run = []
    for row in reversed(rows):
        if abs(row.amount - latest) <= abs(latest) * FIXED_TOLERANCE:
            run.append(row)
        else:
            break
    run.reverse()
    return run


def _build(key, rows, frequency, expected, tolerance, varies, today) -> Candidate:
    categories = Counter(r.category_id for r in rows if r.category_id)
    currencies = Counter(getattr(r, "currency", None) or "SGD" for r in rows)
    accounts = Counter(getattr(r, "account_id", None) for r in rows if getattr(r, "account_id", None))
    last = rows[-1].transaction_date
    return Candidate(
        pattern=key,
        label=suggest_label(key),
        frequency=frequency,
        expected_amount=_cents(expected),
        tolerance=tolerance,
        amount_varies=varies,
        occurrences=len(rows),
        first_date=rows[0].transaction_date,
        last_date=last,
        next_due_date=next_due_on_or_after(last, frequency, today),
        category_id=categories.most_common(1)[0][0] if categories else None,
        currency=currencies.most_common(1)[0][0],
        sample_description=rows[-1].description_raw,
        account_id=accounts.most_common(1)[0][0] if accounts else None,
    )


def _analyse_group(key: str, rows: list, today: date) -> Optional[Candidate]:
    rows = sorted(rows, key=lambda r: r.transaction_date)
    if len(rows) < MIN_OCCURRENCES:
        return None

    # 1) A fixed amount (the latest run of it, so a price rise doesn't hide the pattern).
    run = _latest_fixed_run(rows)
    if len(run) >= MIN_OCCURRENCES:
        frequency = classify_frequency([r.transaction_date for r in run])
        if frequency:
            return _build(key, run, frequency, median([r.amount for r in run]), FIXED_TOLERANCE, False, today)

    # 2) A variable amount — monthly only (a utility bill, not a spending habit).
    amounts = [r.amount for r in rows]
    centre = median(amounts)
    if centre == 0:
        return None
    deviation = max(abs(a - centre) / abs(centre) for a in amounts)
    if deviation <= VARIABLE_MAX_DEVIATION and classify_frequency([r.transaction_date for r in rows], ("monthly",)):
        rounded_up = (deviation / Decimal("0.05")).to_integral_value(rounding=ROUND_CEILING) * Decimal("0.05")
        tolerance = min(Decimal("0.50"), max(Decimal("0.10"), rounded_up))
        return _build(key, rows, "monthly", centre, tolerance, True, today)

    return None


def detect_candidates(transactions: Iterable, today: date, existing_rules: Iterable = ()) -> list:
    """
    transactions: anything with transaction_date, amount, description_raw, category_id, currency.
    existing_rules: (pattern, is_positive) pairs that already have a rule — active, stopped
    or dismissed. Those are never suggested again.
    """
    existing = set(existing_rules)
    earliest = today - timedelta(days=LOOKBACK_DAYS)

    groups = defaultdict(list)
    for t in transactions:
        if not (earliest <= t.transaction_date <= today) or t.amount == 0:
            continue
        normalized = normalize_description(t.description_raw)
        if TOPUP_RE.search(normalized):
            continue
        key = _key_from_normalized(normalized)
        if key:
            groups[(key, t.amount > 0)].append(t)

    candidates = []
    for (key, positive), rows in groups.items():
        if (key, positive) in existing:
            continue
        candidate = _analyse_group(key, rows, today)
        if candidate:
            candidates.append(candidate)

    # Most evidence first; among equals, the most recently seen.
    candidates.sort(key=lambda c: (-c.occurrences, -c.last_date.toordinal()))
    return candidates


# ---- schedule for existing rules ---------------------------------------------------------


class TransactionIndex:
    """Recent transactions grouped by (key, sign), so each rule can find its latest match."""

    def __init__(self, transactions: Iterable):
        self._groups = defaultdict(list)
        for t in transactions:
            if t.amount == 0:
                continue
            key = description_key(t.description_raw)
            if key:
                self._groups[(key, t.amount > 0)].append(t)

    def latest_match(self, pattern: str, expected_amount: Decimal, tolerance: Decimal):
        best = None
        for t in self._groups.get((pattern, expected_amount > 0), []):
            if abs(t.amount - expected_amount) > abs(expected_amount) * tolerance:
                continue
            if best is None or t.transaction_date > best.transaction_date:
                best = t
        return best


def rule_schedule(rule, index: TransactionIndex, today: date) -> dict:
    """
    When did this rule's charge last happen, and when is it next due? Worked out from the
    transactions every time, so a newly imported statement is picked up with nothing to
    keep in sync. The next date is always rolled forward to today or later.
    """
    tolerance = Decimal(rule.amount_tolerance_pct if rule.amount_tolerance_pct is not None else FIXED_TOLERANCE)
    # The interval is the truth; a rule that predates it (or a bare test object) still has
    # only its old frequency name.
    if getattr(rule, "interval_unit", None) and getattr(rule, "interval_count", None):
        interval = Interval(int(rule.interval_count), rule.interval_unit)
    else:
        interval = as_interval(rule.frequency)
    match = None
    if rule.expected_amount:
        match = index.latest_match(rule.merchant_pattern, Decimal(rule.expected_amount), tolerance)

    last = match.transaction_date if match else rule.last_occurred_date
    if last is not None:
        next_due = next_due_on_or_after(last, interval, today)
    elif rule.next_due_date is not None:
        # No occurrence recorded: the stored date is where the series starts (typed in by
        # hand), so it counts itself and then rolls forward from there.
        next_due = next_on_or_after_anchor(rule.next_due_date, interval, today)
    else:
        next_due = None
    return {
        "last_occurred_date": last,
        "next_due_date": next_due,
        # None when nothing matched; the caller falls back to the rule's account, then SGD.
        "currency": getattr(match, "currency", None) if match else None,
    }