"""
Parses Singapore bank e-statement PDFs (DBS/POSB and OCBC savings/debit layouts) into
transactions.

How it works
------------
Each page is converted to layout-preserving text (pdfplumber's layout mode turns the
column alignment into whitespace), then walked line by line:

1. Find the table header (a line naming Withdrawal, Deposit and Balance) and note where
   each of those columns' right edge sits — amounts are right-aligned under their header.
2. A line that starts with a date opens a new transaction. Every amount on that line is
   assigned to withdrawal / deposit / balance by whichever header edge it lines up with.
3. Indented lines without a date are continuation lines of the previous transaction's
   description (POSB/OCBC print reference numbers and payee names this way).
4. "Balance brought forward" / "carried forward" lines give the opening and closing
   balance, which are used to check the parse adds up — opening + every withdrawal and
   deposit must land exactly on the closing balance. That check is the main safeguard
   against a mis-read row silently corrupting someone's data.

The general technique (layout text + per-bank column logic) is a common approach for
statement parsing; this implementation is written independently, against the layouts
described by sample statements, and shares no code with other parsers.

Optionally (MASK_SENSITIVE_NUMBERS, currently off) sensitive numbers inside transaction
text — card, phone, account, NRIC, long references, emails — can be masked down to their
last four digits before anything is stored or returned. Names are never masked.

NOT yet validated against a real statement file — only against synthetic PDFs and text
samples built to match the DBS/POSB and OCBC layouts. Use the /statements/preview endpoint
on a real file before trusting an import.
"""

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

import pdfplumber


class StatementParseError(ValueError):
    """The file isn't a statement this parser can make sense of."""


@dataclass
class ParsedTransaction:
    transaction_date: date
    description: str
    amount: Decimal  # negative = withdrawal, positive = deposit
    balance_after: Optional[Decimal] = None  # as printed if shown, otherwise computed


@dataclass
class ParseResult:
    bank: Optional[str] = None
    account_number: Optional[str] = None
    statement_end: Optional[date] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    transactions: list = field(default_factory=list)
    computed_closing_balance: Optional[Decimal] = None
    reconciled: Optional[bool] = None  # None = couldn't check (no opening/closing found)
    totals_match: Optional[bool] = None  # None = the statement printed no totals line
    warnings: list = field(default_factory=list)
    # Which header line was picked on each page and where its column edges were placed —
    # for diagnosing a real statement that doesn't parse.
    headers: list = field(default_factory=list)
    # One entry per PDF page: whether a table was found, how many rows were read from it,
    # and the brought/carried-forward balances printed on it. Lets a failure be pinned to
    # the page where it happened instead of only "the whole statement doesn't add up".
    pages: list = field(default_factory=list)

    def pages_summary(self) -> list:
        def money(value):
            return str(value) if value is not None else None

        return [
            {
                "page": p["page"],
                "header_found": p["header_found"],
                "rows": p["rows"],
                "brought_forward": money(p["brought_forward"]),
                "carried_forward": money(p["carried_forward"]),
                "net_of_rows": str(p["net"]),
            }
            for p in self.pages
        ]


# Amounts always carry exactly two decimals; reference numbers and FX rates don't match.
AMOUNT_RE = re.compile(r"(?<![\d,.])\d[\d,]*\.\d{2}(?!\d)")
DATE_START_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z]{3})\b")
SECOND_DATE_RE = re.compile(r"\s*(\d{1,2})\s+([A-Za-z]{3})\b")
# Some statements print numeric dates with the year included: "30/09/2026" (day first, as
# Singapore banks do). A two-digit year ("30/09/26") is read as 20xx.
NUMERIC_DATE_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})(?!\d)")
SECOND_NUMERIC_DATE_RE = re.compile(r"\s*\d{1,2}/\d{1,2}/\d{2,4}(?!\d)")

# A header cell may carry a "($)" suffix (DBS) or a Chinese label (OCBC) after the English
# word; amounts align with the right edge of the whole cell, so include those.
HEADER_CELL_RE = re.compile(
    r"(withdrawal|deposit|balance)(?:\(\$\))?(?:\s*[\u3400-\u9fff][\u3400-\u9fff/]*)?",
    re.IGNORECASE,
)
DESCRIPTION_HEADER_RE = re.compile(r"details of transactions|description", re.IGNORECASE)

OPENING_RE = re.compile(r"balance\s+(?:brought\s+forward|b/f)", re.IGNORECASE)
CLOSING_RE = re.compile(r"balance\s+(?:carried\s+forward|c/f)", re.IGNORECASE)
TOTALS_RE = re.compile(r"^\s*total(?:\s+withdrawals\s*/\s*deposits)?\s*$", re.IGNORECASE)
PAGE_FURNITURE_RE = re.compile(r"^\s*page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE)

PERIOD_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+TO\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})",
    re.IGNORECASE,
)
AS_AT_RE = re.compile(r"As\s+at\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", re.IGNORECASE)
ACCOUNT_RE = re.compile(r"Account\s+No\.?:?\s*([\d][\d-]{5,})", re.IGNORECASE)

# Hard-coded rather than strptime("%b"), which depends on the machine's locale.
MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


def _month(abbr: str) -> Optional[int]:
    return MONTHS.get(abbr.lower())


def _to_decimal(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Masking is currently OFF: descriptions and the account number come through exactly as
# printed on the statement. Set this to True to mask card/phone/account/NRIC numbers and
# long references down to their last four digits before anything is stored or returned.
MASK_SENSITIVE_NUMBERS = False

# ---- Masking sensitive numbers --------------------------------------------------------
# A transaction's text is stored word for word, and on a real statement that can include a
# full card number, a payee's phone or account number, or an NRIC. None of that is needed
# for categorising or summarising spending, so digits are masked down to the last four
# before anything is saved or returned. Names can't be recognised reliably, so they are
# NOT masked — merchant names are needed, and payee names are the one thing left.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
NRIC_RE = re.compile(r"\b[STFGM]\d{7}[A-Z]\b", re.IGNORECASE)
SPACED_CARD_RE = re.compile(r"(?<!\d)\d{4}(?:[ -]\d{4}){3}(?!\d)")
SG_PHONE_RE = re.compile(r"(?<!\d)(?:\+?65[ -]?)?[89]\d{3}[ -]?\d{4}(?!\d)")
NUMBER_RUN_RE = re.compile(r"(?<![\d-])\d(?:[\d-]*\d)?(?![\d-])")
MASK_MIN_DIGITS = 7  # a bare run of this many digits or more is treated as an ID/number


def _mask_digits(text: str, keep: int = 4) -> str:
    """Replace every digit with * except the last `keep` digits; other characters stay."""
    total = sum(ch.isdigit() for ch in text)
    seen = 0
    out = []
    for ch in text:
        if ch.isdigit():
            seen += 1
            out.append(ch if seen > total - keep else "*")
        else:
            out.append(ch)
    return "".join(out)


def sanitize_text(text: str) -> str:
    if not MASK_SENSITIVE_NUMBERS:
        return text
    text = EMAIL_RE.sub("[email]", text)
    text = NRIC_RE.sub(lambda m: "*" * (len(m.group()) - 4) + m.group()[-4:], text)
    text = SPACED_CARD_RE.sub(lambda m: _mask_digits(m.group()), text)
    text = SG_PHONE_RE.sub(lambda m: _mask_digits(m.group()), text)
    return NUMBER_RUN_RE.sub(
        lambda m: _mask_digits(m.group())
        if sum(ch.isdigit() for ch in m.group()) >= MASK_MIN_DIGITS
        else m.group(),
        text,
    )


def extract_layout_pages(data: bytes) -> list:
    """PDF bytes -> one layout-preserving text string per page."""
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise StatementParseError(
            "Couldn't open this file as a PDF — it may be password-protected or damaged."
        ) from exc

    pages = []
    with pdf:
        for page in pdf.pages:
            # Statements print things like a registration number sideways down the margin.
            # Dropping rotated characters keeps that out of the text — but only when most of
            # the page IS upright. On a page whose text is rotated as a whole, every
            # character counts as "not upright", and filtering would delete the entire page.
            # (In testing, margin text never actually broke parsing on its own; this is a
            # cheap precaution, deliberately kept from ever being able to empty a page.)
            chars = page.chars
            mostly_upright = bool(chars) and (
                sum(1 for ch in chars if ch.get("upright", True)) / len(chars) >= 0.5
            )
            if mostly_upright:
                page = page.filter(
                    lambda obj: obj.get("object_type") != "char" or obj.get("upright", True)
                )
            pages.append(page.extract_text(layout=True) or "")
    return pages


def _detect_bank(text: str) -> Optional[str]:
    low = text.lower()
    if "ocbc" in low:
        return "ocbc"
    if "posb" in low:
        return "posb"
    if "dbs" in low:
        return "dbs"
    return None


def _find_statement_end(all_lines: list) -> Optional[date]:
    text = "\n".join(all_lines)
    m = PERIOD_RE.search(text)
    if m and _month(m.group(5)):
        try:
            return date(int(m.group(6)), _month(m.group(5)), int(m.group(4)))
        except ValueError:
            pass
    m = AS_AT_RE.search(text)
    if m and _month(m.group(2)):
        try:
            return date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return None


def _find_header(lines: list):
    """Returns (index, column_edges, description_start, two_date_columns) or None."""
    for i, line in enumerate(lines):
        low = line.lower()
        if "withdrawal" in low and "deposit" in low and "balance" in low:
            edges = {}
            for m in HEADER_CELL_RE.finditer(line):
                edges.setdefault(m.group(1).lower(), m.end())
            if len(edges) < 3:
                continue
            desc = DESCRIPTION_HEADER_RE.search(line)
            first_date = re.search(r"\bdate\b", line, re.IGNORECASE)
            desc_start = desc.start() if desc else (first_date.end() + 2 if first_date else 0)
            two_dates = len(re.findall(r"\bdate\b", line, re.IGNORECASE)) >= 2
            return i, edges, desc_start, two_dates
    return None


def parse_layout_pages(pages: list) -> ParseResult:
    result = ParseResult()
    all_lines = [ln for page in pages for ln in page.split("\n")]
    result.bank = _detect_bank("\n".join(all_lines))

    m = ACCOUNT_RE.search("\n".join(all_lines))
    if m:
        result.account_number = (
            _mask_digits(m.group(1), 3) if MASK_SENSITIVE_NUMBERS else m.group(1)
        )

    statement_end = _find_statement_end(all_lines)
    if statement_end is None:
        raise StatementParseError(
            "Couldn't find the statement date (expected 'As at DD Mon YYYY' or a "
            "'DD Mon YYYY TO DD Mon YYYY' period)."
        )
    result.statement_end = statement_end

    def resolve_date(day: int, month: int) -> Optional[date]:
        # Statements print "09 Dec" with no year. A month later than the statement's own
        # month must belong to the previous year (a January statement listing late December).
        year = statement_end.year if month <= statement_end.month else statement_end.year - 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def numeric_date(day: int, month: int, year: int) -> Optional[date]:
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None

    late_dates: list = []  # transactions dated after the statement's own date
    running: Optional[Decimal] = None
    sum_withdrawals = Decimal(0)
    sum_deposits = Decimal(0)
    printed_total_withdrawals: Optional[Decimal] = None
    printed_total_deposits: Optional[Decimal] = None
    found_any_header = False
    unused_date_lines: list = []

    for page_number, page_text in enumerate(pages, 1):
        lines = page_text.split("\n")
        header = _find_header(lines)
        if header is None:
            result.pages.append(
                {"page": page_number, "header_found": False, "rows": 0,
                 "brought_forward": None, "carried_forward": None, "net": Decimal(0)}
            )
            continue
        found_any_header = True
        page_info = {"page": page_number, "header_found": True, "rows": 0,
                     "brought_forward": None, "carried_forward": None, "net": Decimal(0)}
        header_index, edges, desc_start, two_dates = header
        result.headers.append(
            {"page": page_number, "line": _collapse(lines[header_index])[:120], "edges": dict(edges)}
        )

        withdrawal_edge, deposit_edge = edges["withdrawal"], edges["deposit"]
        pitch = max(deposit_edge - withdrawal_edge, 10)
        # Anything ending well left of the withdrawal column is description text
        # (e.g. an FX amount quoted inside a payee name), not a column amount.
        left_bound = withdrawal_edge - int(pitch * 0.75)

        def classify(end_col: int) -> str:
            return min(edges, key=lambda k: abs(edges[k] - end_col))

        pending: Optional[dict] = None
        table_ended = False

        def finalize():
            nonlocal pending, running, sum_withdrawals, sum_deposits
            if pending is None:
                return
            amount = pending["amount"]
            if amount < 0:
                sum_withdrawals += -amount
            else:
                sum_deposits += amount

            if running is not None:
                running += amount
            stated = pending["stated_balance"]
            if stated is not None and running is not None and running != stated:
                result.warnings.append(
                    f"Row {len(result.transactions) + 1} ({pending['date']}, "
                    f"{sanitize_text(_collapse(' '.join(pending['description'])))[:30]}): running balance "
                    f"{running} doesn't match the {stated} printed on the statement."
                )
                running = stated  # resync so one bad row doesn't flag every row after it
            result.transactions.append(
                ParsedTransaction(
                    transaction_date=pending["date"],
                    description=sanitize_text(_collapse(" ".join(pending["description"]))),
                    amount=amount,
                    balance_after=stated if stated is not None else running,
                )
            )
            page_info["rows"] += 1
            page_info["net"] += amount
            pending = None

        for line in lines[header_index + 1 :]:
            if not line.strip() or PAGE_FURNITURE_RE.match(line):
                continue

            amounts_all = [(am.group(), am.end()) for am in AMOUNT_RE.finditer(line)]
            text_without_amounts = _collapse(AMOUNT_RE.sub("", line))

            # Statement totals line ("Total  396.65  1,653.65"): kept as a second check.
            if TOTALS_RE.match(text_without_amounts) and amounts_all:
                for text, end in amounts_all:
                    column = classify(end)
                    if column == "withdrawal":
                        printed_total_withdrawals = _to_decimal(text)
                    elif column == "deposit":
                        printed_total_deposits = _to_decimal(text)
                continue

            if table_ended:
                continue  # anything after the closing balance (legal text etc.) is noise

            if OPENING_RE.search(line):
                finalize()
                if amounts_all and page_info["brought_forward"] is None:
                    page_info["brought_forward"] = _to_decimal(amounts_all[-1][0])
                if amounts_all and result.opening_balance is None:
                    result.opening_balance = _to_decimal(amounts_all[-1][0])
                    running = result.opening_balance
                continue

            if CLOSING_RE.search(line):
                finalize()
                if amounts_all:
                    result.closing_balance = _to_decimal(amounts_all[-1][0])
                    page_info["carried_forward"] = _to_decimal(amounts_all[-1][0])
                table_ended = True
                continue

            named = DATE_START_RE.match(line)
            named = named if (named and _month(named.group(2))) else None
            numeric = None if named else NUMERIC_DATE_RE.match(line)
            starts_with_date = named is not None or numeric is not None

            if starts_with_date:
                if named is not None:
                    pos = named.end()
                    if two_dates:
                        second = SECOND_DATE_RE.match(line, pos)
                        if second and _month(second.group(2)):
                            pos = second.end()
                    parsed_date = resolve_date(int(named.group(1)), _month(named.group(2)))
                else:
                    pos = numeric.end()
                    if two_dates:
                        second = SECOND_NUMERIC_DATE_RE.match(line, pos)
                        if second:
                            pos = second.end()
                    parsed_date = numeric_date(
                        int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3))
                    )

                column_amounts = []
                for am in AMOUNT_RE.finditer(line, pos):
                    if am.end() >= left_bound:
                        column_amounts.append((classify(am.end()), _to_decimal(am.group()), am.start()))

                money = [c for c in column_amounts if c[0] in ("withdrawal", "deposit")]

                if parsed_date is not None and len(money) == 1:
                    finalize()
                    if parsed_date > statement_end:
                        late_dates.append(parsed_date.isoformat())
                    column, value, _ = money[0]
                    balances = [c[1] for c in column_amounts if c[0] == "balance"]
                    first_amount_start = min(c[2] for c in column_amounts)
                    pending = {
                        "date": parsed_date,
                        "description": [line[pos:first_amount_start]],
                        "amount": -value if column == "withdrawal" else value,
                        "stated_balance": balances[-1] if balances else None,
                    }
                    continue

                if parsed_date is not None and len(money) > 1:
                    finalize()
                    result.warnings.append(
                        f"Skipped a line with more than one withdrawal/deposit amount: "
                        f"{sanitize_text(_collapse(line))[:60]}"
                    )
                    continue
                # Otherwise (no money amount, or an impossible date such as 31 Feb) this
                # wasn't read as a transaction — fall through and treat it as text. That is
                # usually right for a stray wrapped line, but if a real transaction row is
                # being missed this is where it would silently vanish, so remember it.
                unused_date_lines.append(sanitize_text(_collapse(line))[:70])

            if pending is not None:
                first_char_col = len(line) - len(line.lstrip())
                # Stray text hugging the left margin isn't part of the description column.
                if first_char_col >= desc_start - 3:
                    pending["description"].append(line)

        finalize()
        result.pages.append(page_info)

    if not found_any_header:
        raise StatementParseError(
            "Couldn't find a transaction table (a header with Withdrawal, Deposit and Balance)."
        )

    if unused_date_lines:
        result.warnings.append(
            f"{len(unused_date_lines)} line(s) started with a date but had no withdrawal/deposit "
            f"amount lined up under a column, so they weren't read as transactions "
            f"(first: '{unused_date_lines[0]}')."
        )

    if late_dates:
        result.warnings.append(
            f"{len(late_dates)} transaction(s) are dated after the statement date "
            f"{statement_end.isoformat()} (e.g. {late_dates[0]}) — check the day/month order."
        )

    # --- Does it add up? ---
    if result.opening_balance is not None and result.closing_balance is not None:
        net = sum((t.amount for t in result.transactions), Decimal(0))
        result.computed_closing_balance = result.opening_balance + net
        result.reconciled = result.computed_closing_balance == result.closing_balance
        if not result.reconciled:
            result.warnings.append(
                f"Opening balance {result.opening_balance} plus the parsed transactions "
                f"comes to {result.computed_closing_balance}, but the statement's closing "
                f"balance is {result.closing_balance}."
            )
    else:
        result.warnings.append("Couldn't find both an opening and closing balance to check against.")

    if printed_total_withdrawals is not None and printed_total_deposits is not None:
        result.totals_match = (
            printed_total_withdrawals == sum_withdrawals and printed_total_deposits == sum_deposits
        )
        if not result.totals_match:
            result.warnings.append(
                f"Statement totals ({printed_total_withdrawals} out / {printed_total_deposits} in) "
                f"don't match the parsed rows ({sum_withdrawals} out / {sum_deposits} in)."
            )

    # Page by page: only worth saying when the statement as a whole didn't add up, and added
    # after every other warning so the most specific explanation is the last one.
    if result.reconciled is not True:
        previous = None
        for info in result.pages:
            if not info["header_found"]:
                if found_any_header:
                    result.warnings.append(
                        f"Page {info['page']}: no transaction table header was found, so "
                        f"nothing was read from it."
                    )
                continue
            bf, cf = info["brought_forward"], info["carried_forward"]
            if previous is not None and previous["carried_forward"] is not None and bf is not None:
                if previous["carried_forward"] != bf:
                    result.warnings.append(
                        f"Page {info['page']} starts at {bf} but page {previous['page']} ended "
                        f"at {previous['carried_forward']} — a page may be missing or unreadable."
                    )
            if bf is not None and cf is not None and bf + info["net"] != cf:
                result.warnings.append(
                    f"Page {info['page']}: brought forward {bf} plus its {info['rows']} parsed "
                    f"row(s) comes to {bf + info['net']}, but the page carries forward {cf}."
                )
            previous = info

    return result


def parse_statement(data: bytes) -> ParseResult:
    return parse_layout_pages(extract_layout_pages(data))


def make_external_id(account_id, transaction: ParsedTransaction, occurrence: int) -> str:
    """
    A stable ID for a statement row, so re-importing the same statement is a no-op rather
    than a pile of duplicates. Statements have no per-transaction ID of their own, so this
    is a hash of the row's content; `occurrence` (1, 2, ...) tells apart genuinely
    identical rows within one statement (two FAST payments of the same amount on one day).
    The account is part of the hash so the same row on two different accounts can't clash.
    """
    raw = "|".join(
        [
            "stmt",
            str(account_id),
            transaction.transaction_date.isoformat(),
            str(transaction.amount),
            transaction.description,
            str(occurrence),
        ]
    )
    return "pdf_" + hashlib.sha256(raw.encode()).hexdigest()[:32]