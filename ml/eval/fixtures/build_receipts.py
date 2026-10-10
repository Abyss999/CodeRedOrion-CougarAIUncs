#!/usr/bin/env python
"""Generates the receipt text fixtures + ground truth in fixtures/receipts/ (NN_name.txt / NN_name.json).

Ground-truth conventions (documented in ml/eval/README.md):
  * `lines` = purchased goods only. Subtotal, tax, discount/coupon, bag-fee, payment, change and
    loyalty lines are NOT items.
  * `price` = the amount charged for that line (the right-hand column), before any separate
    discount line; for "2 @ 1.50  3.00" or "1.2 lb @ 2.00/lb  2.40", quantity is 2 / 1.2 and price 3.00 / 2.40.
  * `total` = the amount actually paid (the TOTAL / BALANCE DUE line, after tax and discounts).
Each entry carries `adj` = taxes - discounts + fees so this script can assert items + adj == total.
Run:  python ml/eval/fixtures/build_receipts.py
"""
import json, os

R = []
def add(name, text, lines, total, adj):
    s = round(sum(l[2] for l in lines) + adj, 2)
    assert abs(s - total) < 0.005, f"{name}: items+adj={s} != total={total}"
    R.append((name, text.strip("\n") + "\n", [{"name": n, "quantity": q, "price": p} for n, q, p in lines], total))

add("01_safeway_simple", """
SAFEWAY
1234 MARKET ST  SAN FRANCISCO CA
03/14/2026 10:42AM  STORE 0412
--------------------------------
MILK 2% GAL              4.29
LG EGGS 12CT             3.99
BANANAS ORG              1.87
SOURDOUGH LOAF           4.50
SUBTOTAL                14.65
TAX                      0.00
TOTAL                   14.65
VISA ****1234
THANK YOU FOR SHOPPING
""", [("MILK 2% GAL", 1, 4.29), ("LG EGGS 12CT", 1, 3.99), ("BANANAS ORG", 1, 1.87), ("SOURDOUGH LOAF", 1, 4.50)], 14.65, 0)

add("02_walmart_tax_upc", """
WALMART SUPERCENTER
STORE #2231  (555) 010-7788
GV WHL MILK GAL       078742013251 F   3.58
GV LARGE EGG 18       078742127217 F   4.62
BANANAS               000000040111 F   0.92
CHKN BRST BNLS        026024410018 F   9.74
FROZ PEAS 12OZ        078742231471 F   1.28
SUBTOTAL                              20.14
TAX 1  6.250 %                         0.00
TOTAL                                 20.14
CASH TEND                             40.00
CHANGE DUE                            19.86
# ITEMS SOLD 5
""", [("GV WHL MILK GAL", 1, 3.58), ("GV LARGE EGG 18", 1, 4.62), ("BANANAS", 1, 0.92), ("CHKN BRST BNLS", 1, 9.74), ("FROZ PEAS 12OZ", 1, 1.28)], 20.14, 0)

add("03_trader_weighted", """
TRADER JOE'S #145
Organic Bananas
  2.34 lb @ $0.79/lb          $1.85
Honeycrisp Apples
  1.60 lb @ $2.99/lb          $4.78
Whole Milk Gallon             $4.49
Mandarin Oranges Bag          $3.99
SUBTOTAL                     $15.11
SALES TAX                     $0.00
TOTAL                        $15.11
""", [("Organic Bananas", 2.34, 1.85), ("Honeycrisp Apples", 1.60, 4.78), ("Whole Milk Gallon", 1, 4.49), ("Mandarin Oranges Bag", 1, 3.99)], 15.11, 0)

add("04_qty_times_price", """
KROGER
01/09/2026
3 @ 1.25  GREEK YOGURT      3.75
2 @ 0.99  BANANAS           1.98
1 @ 5.49  RIBEYE STEAK      5.49
4 @ 0.50  LIMES             2.00
  SUBTOTAL                 13.22
  TOTAL                    13.22
""", [("GREEK YOGURT", 3, 3.75), ("BANANAS", 2, 1.98), ("RIBEYE STEAK", 1, 5.49), ("LIMES", 4, 2.00)], 13.22, 0)

add("05_coupon_discount", """
TARGET
BREAD WHOLE WHEAT         3.29
CHEDDAR SHARP 8OZ         2.79
   COUPON 20% OFF       -0.56
ORANGE JUICE 52OZ         3.99
SUBTOTAL                  9.51
TAX                       0.00
TOTAL                     9.51
""", [("BREAD WHOLE WHEAT", 1, 3.29), ("CHEDDAR SHARP 8OZ", 1, 2.79), ("ORANGE JUICE 52OZ", 1, 3.99)], 9.51, -0.56)

add("06_subtotal_vs_total_tax", """
WHOLE FOODS MARKET
365 ORG SPINACH 10OZ          3.49
SALMON FILLET                12.99
AVOCADO HASS                  1.50
ALMOND MILK UNSWEET           3.29
Subtotal                     21.27
Sales Tax 8.5%                1.81
Total                        23.08
Amex xxxx2001                23.08
""", [("365 ORG SPINACH 10OZ", 1, 3.49), ("SALMON FILLET", 1, 12.99), ("AVOCADO HASS", 1, 1.50), ("ALMOND MILK UNSWEET", 1, 3.29)], 23.08, 1.81)

add("07_aldi_short", """
ALDI
BUTTER UNSALTED   3.15
CREAM CHEESE      1.89
SPAGHETTI         0.95
TOMATO SAUCE      1.19
BALANCE DUE       7.18
""", [("BUTTER UNSALTED", 1, 3.15), ("CREAM CHEESE", 1, 1.89), ("SPAGHETTI", 1, 0.95), ("TOMATO SAUCE", 1, 1.19)], 7.18, 0)

add("08_costco_bulk", """
COSTCO WHOLESALE #1002
E 1234567 KS ORG EGGS 24CT      9.99
E 7654321 ROTISSERIE CHICKEN    4.99
E 1112223 KS BUTTER 4PK        11.49
E 9998887 STRAWBERRIES 2LB      7.99
SUBTOTAL                       34.46
TAX                             0.00
**** TOTAL                     34.46
""", [("KS ORG EGGS 24CT", 1, 9.99), ("ROTISSERIE CHICKEN", 1, 4.99), ("KS BUTTER 4PK", 1, 11.49), ("STRAWBERRIES 2LB", 1, 7.99)], 34.46, 0)

add("09_weighted_deli", """
PUBLIX
DELI TURKEY BREAST
  0.75 lb @ 8.99 /lb         6.74
SWISS CHEESE SLICED
  0.50 lb @ 7.49 /lb         3.75
ROMA TOMATOES
  1.12 lb @ 1.99 /lb         2.23
SUBTOTAL                    12.72
TOTAL                       12.72
""", [("DELI TURKEY BREAST", 0.75, 6.74), ("SWISS CHEESE SLICED", 0.50, 3.75), ("ROMA TOMATOES", 1.12, 2.23)], 12.72, 0)

add("10_cvs_loyalty_savings", """
CVS/pharmacy
GATORADE 28OZ         1.99
   ExtraCare Savings  -0.50
PEANUT BUTTER 16OZ    3.29
CHEWY GRANOLA BARS    2.50
SUBTOTAL              7.28
TAX                   0.45
TOTAL                 7.73
YOU SAVED             0.50
""", [("GATORADE 28OZ", 1, 1.99), ("PEANUT BUTTER 16OZ", 1, 3.29), ("CHEWY GRANOLA BARS", 1, 2.50)], 7.73, -0.50 + 0.45)

add("11_lowercase_pos", """
corner market
2026-02-02 18:20
apples gala x3      3.60
bread rye           2.80
milk oat 1l         2.45
total               8.85
cash                10.00
""", [("apples gala", 3, 3.60), ("bread rye", 1, 2.80), ("milk oat 1l", 1, 2.45)], 8.85, 0)

add("12_dollar_signs_tab", """
Lucky Supermarket
Chicken Thighs Bone-In	$8.47
Baby Carrots 1lb	$1.99
Cottage Cheese 16oz	$3.19
Frozen Pizza Margherita	$5.99
Subtotal	$19.64
Tax	$0.00
Total	$19.64
""", [("Chicken Thighs Bone-In", 1, 8.47), ("Baby Carrots 1lb", 1, 1.99), ("Cottage Cheese 16oz", 1, 3.19), ("Frozen Pizza Margherita", 1, 5.99)], 19.64, 0)

add("13_bag_fee_and_deposit", """
SAFEWAY
SPARKLING WATER 12PK        5.99
CRV DEPOSIT                 0.60
BREAD MULTIGRAIN            3.99
PAPER BAG FEE               0.10
SUBTOTAL                   10.68
TAX                         0.00
TOTAL                      10.68
""", [("SPARKLING WATER 12PK", 1, 5.99), ("BREAD MULTIGRAIN", 1, 3.99)], 10.68, 0.70)

add("14_multi_discount", """
FRED MEYER
YOGURT STRAWBERRY 6OZ   0.89
YOGURT STRAWBERRY 6OZ   0.89
YOGURT STRAWBERRY 6OZ   0.89
   MULTI-SAVE 3 FOR 2   -0.89
CHICKEN BROTH 32OZ      2.19
SUBTOTAL                3.97
TOTAL                   3.97
""", [("YOGURT STRAWBERRY 6OZ", 1, 0.89), ("YOGURT STRAWBERRY 6OZ", 1, 0.89), ("YOGURT STRAWBERRY 6OZ", 1, 0.89), ("CHICKEN BROTH 32OZ", 1, 2.19)], 3.97, -0.89)

add("15_heb_sale_tags", """
H-E-B
PICO DE GALLO        2.98  S
LIMES 1LB            1.24  S
  REG 1.68  SALE SAVINGS 0.44
TORTILLAS CORN 30CT  1.89
CILANTRO BUNCH       0.68
SUBTOTAL             6.79
TAX                  0.00
TOTAL                6.79
""", [("PICO DE GALLO", 1, 2.98), ("LIMES 1LB", 1, 1.24), ("TORTILLAS CORN 30CT", 1, 1.89), ("CILANTRO BUNCH", 1, 0.68)], 6.79, 0)

add("16_asian_market", """
99 RANCH MARKET
NAPA CABBAGE
  3.20 lb @ 0.69/lb     2.21
TOFU FIRM 14OZ          1.79
SHRIMP RAW 1LB          8.99
JASMINE RICE 5LB        7.49
TOTAL                  20.48
""", [("NAPA CABBAGE", 3.20, 2.21), ("TOFU FIRM 14OZ", 1, 1.79), ("SHRIMP RAW 1LB", 1, 8.99), ("JASMINE RICE 5LB", 1, 7.49)], 20.48, 0)

add("17_wegmans_two_line", """
WEGMANS
Item                      Qty    Price
Organic Whole Milk          1     5.29
Grass-Fed Butter            2     9.98
Fresh Mozzarella            1     4.49
Baguette                    1     2.99
                  Subtotal     22.75
                       Tax      0.00
                     Total     22.75
""", [("Organic Whole Milk", 1, 5.29), ("Grass-Fed Butter", 2, 9.98), ("Fresh Mozzarella", 1, 4.49), ("Baguette", 1, 2.99)], 22.75, 0)

add("18_sprouts_produce_weights", """
SPROUTS FARMERS MARKET
ORG KALE BUNCH           2.49
BROCCOLI CROWN
 1.45 lb @ 1.99/lb       2.89
YELLOW ONIONS
 3.00 lb @ 0.99/lb       2.97
SWEET POTATO
 2.10 lb @ 1.29/lb       2.71
Sub Total               11.06
Total                   11.06
""", [("ORG KALE BUNCH", 1, 2.49), ("BROCCOLI CROWN", 1.45, 2.89), ("YELLOW ONIONS", 3.00, 2.97), ("SWEET POTATO", 2.10, 2.71)], 11.06, 0)

add("19_ocr_noisy_spacing", """
SAFEWAY
M ILK  2 %  GAL           4 .29
EGGS  LARGE  DOZ          3.99
SPINACH  BABY             2.99
SUBTOTAL                 11.27
TOTAL                    11.27
""", [("MILK 2% GAL", 1, 4.29), ("EGGS LARGE DOZ", 1, 3.99), ("SPINACH BABY", 1, 2.99)], 11.27, 0)

add("20_big_receipt_tax_flag", """
SAVE MART
01 BANANAS ORGANIC        1.29
02 GROUND BEEF 80/20      6.99
03 YELLOW ONIONS          1.79
04 CANNED BLACK BEANS     0.99
05 CANNED BLACK BEANS     0.99
06 SHREDDED CHEESE        3.49
07 SOUR CREAM             1.99
08 TORTILLAS FLOUR        2.49
09 SALSA MEDIUM           2.99
10 PAPER TOWELS  T        6.99
SUBTOTAL                 30.00
TAX                       0.60
TOTAL                    30.60
""", [("BANANAS ORGANIC", 1, 1.29), ("GROUND BEEF 80/20", 1, 6.99), ("YELLOW ONIONS", 1, 1.79), ("CANNED BLACK BEANS", 1, 0.99), ("CANNED BLACK BEANS", 1, 0.99), ("SHREDDED CHEESE", 1, 3.49), ("SOUR CREAM", 1, 1.99), ("TORTILLAS FLOUR", 1, 2.49), ("SALSA MEDIUM", 1, 2.99), ("PAPER TOWELS", 1, 6.99)], 30.60, 0.60)

add("21_euro_style", """
LIDL
Bananen            1,29
Vollmilch 1L       0,95
Joghurt Natur      0,49
Brot Vollkorn      1,79
SUMME EUR          4,52
""", [("Bananen", 1, 1.29), ("Vollmilch 1L", 1, 0.95), ("Joghurt Natur", 1, 0.49), ("Brot Vollkorn", 1, 1.79)], 4.52, 0)

add("22_returns_and_tender", """
SAFEWAY
CHICKEN WINGS 2LB        7.99
RANCH DRESSING           2.89
CELERY STALKS            1.79
SUBTOTAL                12.67
TAX                      0.00
TOTAL                   12.67
DEBIT TEND              12.67
CHANGE                   0.00
REWARDS POINTS EARNED      12
CARD BALANCE            57.30
""", [("CHICKEN WINGS 2LB", 1, 7.99), ("RANCH DRESSING", 1, 2.89), ("CELERY STALKS", 1, 1.79)], 12.67, 0)

add("23_qty_in_name_x", """
FOOD LION
BANANAS X5          2.45
YOGURT CUP X4       3.16
LETTUCE ROMAINE     1.99
TOTAL               7.60
""", [("BANANAS", 5, 2.45), ("YOGURT CUP", 4, 3.16), ("LETTUCE ROMAINE", 1, 1.99)], 7.60, 0)

add("24_grand_total_label", """
Meijer
Frozen Waffles 10ct      3.49
Maple Syrup              4.99
Pork Chops Thick         7.88
Items: 3
Merchandise Total       16.36
Sales Tax                0.00
GRAND TOTAL             16.36
""", [("Frozen Waffles 10ct", 1, 3.49), ("Maple Syrup", 1, 4.99), ("Pork Chops Thick", 1, 7.88)], 16.36, 0)

here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "receipts")
os.makedirs(out, exist_ok=True)
seen = set()
for name, text, lines, total in R:
    if name in seen:
        continue
    seen.add(name)
    with open(os.path.join(out, name + ".txt"), "w") as f:
        f.write(text)
    with open(os.path.join(out, name + ".json"), "w") as f:
        json.dump({"receipt": name, "lines": lines, "total": total}, f, indent=1)
print(len(seen), "receipts written")
