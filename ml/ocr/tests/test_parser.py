import pytest
from ocr.receipt_pipeline import parse_receipt_text, gemini_structure

KROGER = """KROGER
1234 MAIN ST ANYTOWN
(555) 123-4567
03/14/2026 05:42 PM
GV 2% MILK GAL             3.48 F
BANANAS
 1.23 lb @ $0.59/lb        0.73 F
KRO BREAD WHT              1.99 F
2 @ 1.50
  ORG EGGS LRG             3.00
SCAN COUPON  MFR           1.00-
SAVINGS                   -0.50
SUBTOTAL                   9.20
TAX                        0.00
TOTAL                      9.20
VISA ****1234              9.20
THANK YOU FOR SHOPPING
"""

WALMART = """WALMART
ST# 1234 OP# 009 TE# 06 TR# 05021
GV PNT BUTTR 007874202517 4.98 F
BANANAS 000000040111K 1.12 N
  1.88 lb @ 1 lb /0.58
AVOCADO 4 8 1.00 x 3 3.00 N
SUBTOTAL 9.10
TAX 1 6.250 % 0.31
TOTAL 9.41
DEBIT TEND 9.41
CHANGE DUE 0.00
# ITEMS SOLD 4
"""

TARGET_SPLIT = """TARGET
Good&Gather Spinach
3.29
Chobani Greek Yogurt
2 x $1.25
2.50
Tomatoes on vine 2.04 lb @ $2.99/lb
6.10
Balance Due
$ 11.89
"""

MARKDOWN = """| Item | Price |
|---|---|
| **CHKN BRST BNLS** | 7.84 |
| RED PEPPER | 1.12 |
| SUBTOTAL | 8.96 |
| TOTAL | 8.96 |
"""


def names(r): return [l["name"] for l in r["lines"]]


def test_kroger_basic_and_exclusions():
    r = parse_receipt_text(KROGER)
    assert names(r) == ["GV 2% MILK GAL", "BANANAS", "KRO BREAD WHT", "ORG EGGS LRG"]
    by = {l["name"]: l for l in r["lines"]}
    assert by["GV 2% MILK GAL"]["price"] == 3.48 and by["GV 2% MILK GAL"]["quantity"] == 1.0
    assert by["BANANAS"]["quantity"] == 1.23 and by["BANANAS"]["price"] == 0.73
    assert "ORG EGGS LRG" in by
    assert not any("COUPON" in n or "SAVINGS" in n or "VISA" in n or "TAX" in n for n in by)
    assert all(l["price"] is None or l["price"] >= 0 for l in r["lines"])
    assert r["total"] == 9.20


def test_qty_at_on_following_line_attaches_to_name():
    r = parse_receipt_text("KRO BREAD WHT\n2 @ 1.50\nTOTAL 3.00\n")
    assert r["lines"][0]["name"] == "KRO BREAD WHT"
    assert r["lines"][0]["quantity"] == 2 and r["lines"][0]["price"] == 3.00


def test_walmart_codes_weighted_and_tax():
    r = parse_receipt_text(WALMART)
    by = {l["name"]: l for l in r["lines"]}
    assert "GV PNT BUTTR" in by and by["GV PNT BUTTR"]["price"] == 4.98
    ban = next(l for l in r["lines"] if l["name"].startswith("BANANAS"))
    assert ban["quantity"] == 1.88 and ban["price"] == 1.12
    assert r["total"] == 9.41
    av = next(l for l in r["lines"] if l["name"].startswith("AVOCADO"))
    assert av["quantity"] == 1.0 and av["price"] == 3.00
    assert not any("TEND" in n or "CHANGE" in n for n in names(r))


def test_split_label_price_columns():
    r = parse_receipt_text(TARGET_SPLIT)
    by = {l["name"]: l for l in r["lines"]}
    assert by["Good&Gather Spinach"]["price"] == 3.29
    assert by["Chobani Greek Yogurt"]["quantity"] == 2 and by["Chobani Greek Yogurt"]["price"] == 2.50
    tom = next(l for l in r["lines"] if l["name"].startswith("Tomatoes"))
    assert tom["quantity"] == 2.04 and tom["price"] == 6.10
    assert r["total"] == 11.89


def test_markdown_table_output():
    r = parse_receipt_text(MARKDOWN)
    assert names(r) == ["CHKN BRST BNLS", "RED PEPPER"]
    assert r["total"] == 8.96


def test_abbreviations_kept_and_no_invented_total():
    r = parse_receipt_text("ORG BNLS SKNLS CHKN THGH 5.99\n")
    assert names(r) == ["ORG BNLS SKNLS CHKN THGH"] and r["total"] is None


def test_total_items_line_is_not_total():
    r = parse_receipt_text("MILK 3.00\nTOTAL SAVINGS 1.00\nTOTAL 3.00\n")
    assert r["total"] == 3.00


def test_empty_and_garbage():
    assert parse_receipt_text("") == {"lines": [], "total": None}
    assert parse_receipt_text("\n\n---\n|||\n")["lines"] == []


def test_gemini_skipped_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gemini_structure("MILK 3.00") is None


def test_qty_first_layout():
    r = parse_receipt_text("3 @ 1.25  GREEK YOGURT      3.75\n4 @ 0.50  LIMES   2.00\nTOTAL 5.75\n")
    assert [(l["name"], l["quantity"], l["price"]) for l in r["lines"]] == [
        ("GREEK YOGURT", 3.0, 3.75), ("LIMES", 4.0, 2.00)]


def test_trailing_upc_and_flag_stripped():
    r = parse_receipt_text("GV WHL MILK GAL       078742013251 F   3.58\nBANANAS 000000040111K 1.12\n")
    assert names(r) == ["GV WHL MILK GAL", "BANANAS"]


def test_leading_store_item_number_stripped():
    r = parse_receipt_text("E 1234567 KS ORG EGGS 24CT      9.99\n7654321 ROTISSERIE CHICKEN  4.99\n")
    assert names(r) == ["KS ORG EGGS 24CT", "ROTISSERIE CHICKEN"]


def test_any_star_total_line_is_not_an_item():
    r = parse_receipt_text("Maple Syrup  4.99\nMerchandise Total  4.99\nGRAND TOTAL  4.99\n")
    assert names(r) == ["Maple Syrup"] and r["total"] == 4.99


def test_euro_total_and_spaced_decimal():
    r = parse_receipt_text("Bananen   1,29\nSUMME EUR   1,29\n")
    assert names(r) == ["Bananen"] and r["total"] == 1.29
    assert parse_receipt_text("EGGS  LARGE   4 .29\n")["lines"][0]["price"] == 4.29
