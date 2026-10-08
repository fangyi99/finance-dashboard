"""
Makes a statement safe to share for debugging the parser.

Reads a statement PDF on your own computer (nothing is uploaded) and writes masked.txt.
Every letter and digit is replaced one-for-one, so column spacing is identical, EXCEPT
the things the parser needs to see:

  kept:    dates ("09 Dec", "31 Dec 2022", "30/09/2026"), money amounts ("1,735.10"), and the structural
           words of the table (Date, Withdrawal, Deposit, Balance, Brought Forward, ...)
  masked:  names, addresses, merchants, payees, account/phone/reference numbers, emails —
           every other letter becomes x/X and every other digit becomes 9

Run from your backend folder with the venv active:

    python mask_statement.py "C:\\path\\to\\statement.pdf"

Then SKIM masked.txt before sharing it. It's built to be conservative, but you're the one
who knows what's on your statement.
"""

import re
import sys

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

# Words that describe the table rather than the person. Anything not listed is masked.
KEEP = {
    "date", "value", "transaction", "transactions", "details", "of", "description",
    "particulars", "narrative", "reference", "ref", "cheque", "chq", "withdrawal",
    "withdrawals", "deposit", "deposits", "debit", "credit", "balance", "opening",
    "closing", "brought", "carried", "forward", "total", "interest", "average", "as",
    "at", "to", "from", "page", "account", "no", "statement", "period", "sgd",
    "summary", "paid", "this", "year", "bank", "dbs", "posb", "ocbc", "uob",
}

TOKEN = re.compile(
    rf"(?P<amount>(?<![\d,.])\d[\d,]*\.\d{{2}}(?!\d))"
    rf"|(?P<date>\b\d{{1,2}}\s+(?:{MONTHS})(?:\s+\d{{4}})?\b)"
    r"|(?P<numdate>(?<![\d/])\d{1,2}/\d{1,2}/\d{2,4}(?![\d/]))"
    r"|(?P<slash>\b[bc]/f\b)"
    r"|(?P<word>[A-Za-z]+)"
    r"|(?P<cjk>[\u3400-\u9fff]+)"
    r"|(?P<digits>\d+)",
    re.IGNORECASE,
)


def _mask_word(word: str) -> str:
    return "".join("X" if ch.isupper() else "x" for ch in word)


def mask_line(line: str) -> str:
    def replace(match):
        kind = match.lastgroup
        text = match.group()
        if kind in ("amount", "date", "numdate", "slash"):
            return text
        if kind == "word":
            return text if text.lower() in KEEP else _mask_word(text)
        if kind == "cjk":
            return "中" * len(text)
        return "9" * len(text)

    return TOKEN.sub(replace, line)


def mask_pages(pages: list) -> str:
    masked = ["\n".join(mask_line(ln) for ln in page.split("\n")) for page in pages]
    return "\n=====PAGE BREAK=====\n".join(masked)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('Usage: python mask_statement.py "path\\to\\statement.pdf"')

    from app.pdf_parser import extract_layout_pages

    pages = extract_layout_pages(open(sys.argv[1], "rb").read())
    with open("masked.txt", "w", encoding="utf-8") as f:
        f.write(mask_pages(pages))
    print(f"Wrote masked.txt ({len(pages)} page(s)). Skim it before sharing.")