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


# ---- ML-7: generalised total detection
@pytest.mark.parametrize("label", ["Balance to pay", "BALANCE TO PAY", "Balance Due", "Amount Due",
                                   "Total Due", "You Pay", "ORDER TOTAL", "Order total", "total"])
def test_total_label_variants(label):
    r = parse_receipt_text(f"STORE\nBANANAS  1.50\nMILK  2.25\nSubtotal  3.75\nTax 0.00\n{label}  $23.83\n")
    assert r["total"] == 23.83
    assert names(r) == ["BANANAS", "MILK"]


def test_total_label_split_and_dollar():
    r = parse_receipt_text("EGGS 3.00\nBalance to pay\n$ 3.00\nVISA 3.00\n")
    assert r["total"] == 3.0 and names(r) == ["EGGS"]


def test_summary_totals_stay_out():
    r = parse_receipt_text("APPLES 2.00\nMerchandise Total 2.00\nItem Total 2.00\nTotal Savings 0.50\n"
                           "Total Tax 0.10\nSubtotal 2.00\nTOTAL 2.10\n")
    assert names(r) == ["APPLES"] and r["total"] == 2.10


# ---- ML-8: voids
@pytest.mark.parametrize("void", ["VOID ORGANIC KALE -2.49", "VOIDED ORGANIC KALE -2.49",
                                  "** VOID ** ORGANIC KALE 2.49-", "ITEM VOID ORGANIC KALE  -2.49",
                                  "Void: Organic Kale (2.49)".replace("(2.49)", "-2.49"), "VOID KALE ORGANIC -2.49"])
def test_void_cancels_item(void):
    r = parse_receipt_text(f"STORE\nSPINACH 3.00\nORGANIC KALE 2.49\n{void}\nMILK 1.00\nTOTAL 4.00\n")
    assert names(r) == ["SPINACH", "MILK"] and r["total"] == 4.0


def test_void_removes_latest_duplicate_only():
    r = parse_receipt_text("YOGURT 1.00\nYOGURT 1.00\nVOID YOGURT -1.00\nTOTAL 1.00\n")
    assert names(r) == ["YOGURT"]


def test_void_unmatched_is_dropped():
    r = parse_receipt_text("MILK 1.00\nVOID ORGANIC KALE -2.49\n** VOID **\nBREAD 2.00\nTOTAL 3.00\n")
    assert names(r) == ["MILK", "BREAD"]
    assert parse_receipt_text("VOID")["lines"] == []


def test_void_price_must_match():
    r = parse_receipt_text("KALE 2.49\nKALE 5.00\nVOID KALE -5.00\nTOTAL 2.49\n")
    assert [l["price"] for l in r["lines"]] == [2.49]


# ---- ML-9: multi-buy
@pytest.mark.parametrize("line,q,price", [
    ("3 @ 2/$5.00 GREEN ONIONS  7.50", 3, 7.50),
    ("3 @ 2 for $5.00 GREEN ONIONS  7.50", 3, 7.50),
    ("4 @ 3/$10.00  GREEN ONIONS 13.33", 4, 13.33),
    ("GREEN ONIONS 2 @ 2/$5.00  5.00", 2, 5.00),
])
def test_multibuy(line, q, price):
    r = parse_receipt_text(f"STORE\n{line}\nTOTAL {price}\n")
    assert len(r["lines"]) == 1
    l = r["lines"][0]
    assert l["name"] == "GREEN ONIONS" and l["quantity"] == q and l["price"] == price


def test_multibuy_split_lines():
    r = parse_receipt_text("GREEN ONIONS\n3 @ 2/$5.00\n7.50\nTOTAL 7.50\n")
    assert r["lines"][0]["name"] == "GREEN ONIONS" and r["lines"][0]["quantity"] == 3


# ---- ML-10: skip words inside real product names must not drop the item
@pytest.mark.parametrize("name", [
    "INSTANT OATMEAL 10CT", "Instant Ramen 5pk", "Credit Card Cookies", "Coupon Clipper", "Discount Bread Co",
    "Promo Pack Gum", "Change Purse Candy", "Debit Card Biscuits", "Member's Mark Water", "Cash Cow Jerky",
    "Club Soda", "Rewards Blend Coffee", "Sugar Snap Peas", "Points Of Light Tea", "Savings Bond Bagels",
    "Phone Home Popcorn", "Tender Greens", "Visa Versa Salsa", "Register Reserve Wine", "Lane Farms Eggs",
    "Welcome Mat Granola", "Auth Entic Rice", "Trans Pacific Noodles", "Discover Crackers", "Account Ability Bars",
])
def test_skip_words_in_product_names(name):
    r = parse_receipt_text(f"S\n{name} 3.79\nTOTAL 3.79\n")
    assert len(r["lines"]) == 1 and r["lines"][0]["price"] == 3.79, name
    assert r["total"] == 3.79


def test_instant_oatmeal_repro():
    assert names(parse_receipt_text("S\nINSTANT OATMEAL 10CT 3.79\nTOTAL 3.79")) == ["INSTANT OATMEAL 10CT"]


@pytest.mark.parametrize("line", [
    "INSTANT SAVINGS 1.00", "Instant Savings -1.00", "COUPON -0.50", "COUPON 0.50", "MEMBER DISCOUNT 0.50",
    "CHANGE DUE 0.00", "CHANGE 0.50", "VISA ****1234 9.41", "VISA 9.41", "CREDIT CARD TEND 9.41", "DEBIT TEND 9.41",
    "CASH 20.00", "CASH TEND 20.00", "PROMO 1.00", "Store Coupon Milk -1.00", "Instant Rebate Discount -2.00",
    "REWARDS POINTS 120.00", "POINTS EARNED 25.00", "MASTERCARD XXXXXXXXXXXX1234 9.41", "AMEX PAYMENT 9.41",
    "YOU SAVED 2.00", "EBT SNAP TEND 9.41", "CLUB CARD SAVINGS 0.75", "TOTAL SAVINGS 3.00",
])
def test_genuine_non_items_still_skipped(line):
    r = parse_receipt_text(f"S\nMILK 1.00\n{line}\nBREAD 2.00\n")
    assert names(r) == ["MILK", "BREAD"], line
