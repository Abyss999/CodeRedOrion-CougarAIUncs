#!/usr/bin/env python
"""Generates BLIND holdout v2 in fixtures/receipts_holdout_v2/. The builder must NOT read this directory
(v1 was used to fix ML-7/8/9, so v2 is the current generalisation set). Same GT conventions as
build_receipts.py/build_holdout.py: items only; price = line total charged; total = amount paid.
Voided items: neither the original line nor the VOID line is an item. A void with no matching item
line (item was on an earlier page/receipt) is also not an item; its negative amount is an adjustment.
Placeholders in the text: {S} item sum, {T} total, {A} sum of adjustments (abs), computed from GT so the
printed numbers are always consistent; add() still asserts items + adjustments == total."""
import json, os
R = []
def add(name, text, lines, adj, **extra):
    s = round(sum(l[2] for l in lines), 2)
    total = round(s + adj, 2)
    assert abs(s + adj - total) < 0.005
    fmt = dict(S="%.2f" % s, T="%.2f" % total, A="%.2f" % abs(adj), **extra)
    R.append((name, text.strip("\n").format(**fmt) + "\n", [{"name": n, "quantity": q, "price": p} for n, q, p in lines], total))


add("v01_kroger_balance_due", """
KROGER
Fuel Points Member
SIMPLE TRUTH ORG MILK       5.49
HNY NUT CHEERIOS 12OZ       4.29
KRO LG EGGS 18CT            3.99
BANANAS
  1.30 lb @ $0.59/lb        0.77
KRO SHRP CHEDDAR 8OZ        2.50
   Instant Savings         -1.00
SAVINGS TOTAL               1.00
SUBTOTAL                   {S}
Total Tax                   0.00
Balance Due                {T}
""", [("SIMPLE TRUTH ORG MILK",1,5.49),("HNY NUT CHEERIOS 12OZ",1,4.29),("KRO LG EGGS 18CT",1,3.99),("BANANAS",1.30,0.77),("KRO SHRP CHEDDAR 8OZ",1,2.50)], -1.00)

add("v02_publix_amount_due_bogo", """
Publix Super Markets #1204
Where shopping is a pleasure
PUBLIX SUB DELI TURKEY      8.99
BUY 1 GET 1 FREE
  PBX SMOKED GOUDA 6OZ      4.19
  PBX SMOKED GOUDA 6OZ      4.19
   BOGO Free               -4.19
GV CUBAN BREAD              2.25
BLUEBERRIES 6OZ             3.50
Item Total                 {S}
Total Savings               4.19
Sales Tax                   0.00
AMOUNT DUE                 {T}
""", [("PUBLIX SUB DELI TURKEY",1,8.99),("PBX SMOKED GOUDA 6OZ",1,4.19),("PBX SMOKED GOUDA 6OZ",1,4.19),("GV CUBAN BREAD",1,2.25),("BLUEBERRIES 6OZ",1,3.50)], -4.19)

add("v03_sprouts_you_pay_void_after", """
SPROUTS FARMERS MARKET
Store 311
ORG GALA APPLES
  2.04 lb @ $1.99/lb        4.06
BULK ALMONDS RAW
  0.55 lb @ $7.99/lb        4.39
KOMBUCHA GINGER 16OZ        3.49
ORG AVOCADO                 1.50
CHIA SEEDS 12OZ             5.99
VOID  KOMBUCHA GINGER 16OZ -3.49
Subtotal                   {S}
Total Savings               0.00
You Pay                    {T}
""", [("ORG GALA APPLES",2.04,4.06),("BULK ALMONDS RAW",0.55,4.39),("ORG AVOCADO",1,1.50),("CHIA SEEDS 12OZ",1,5.99)], 0.0)

add("v04_safeway_multibuy_order_total", """
SAFEWAY #0733
BONELESS CHICKEN BRST       9.84
2 @ 3/$4.00 SPARKLING WATER 2.67
4 @ 2 for $5 CLEMENTINES   10.00
O ORGANICS SPINACH 10OZ     3.49
LUCERNE 2% MILK GAL         4.29
SIGNATURE SELECT BREAD      2.19
Club Card Savings          -2.50
Total Savings               2.50
Order Total                {T}
""", [("BONELESS CHICKEN BRST",1,9.84),("SPARKLING WATER",2,2.67),("CLEMENTINES",4,10.00),("O ORGANICS SPINACH 10OZ",1,3.49),("LUCERNE 2% MILK GAL",1,4.29),("SIGNATURE SELECT BREAD",1,2.19)], -2.50)

add("v05_costco_business_total_due", """
COSTCO BUSINESS CENTER
Member 1118 4402 7731
E 1087232 KS CHICKEN BREAST     17.89
E 5557 KS PAPER TOWEL 12CT      22.99
E 20481 FRESH MOZZ 2LB           8.49
E 77711 COKE ZERO 35PK          21.49
E 31744 ORG SALAD KIT            4.99
VOID  E 77711 COKE ZERO 35PK   -21.49
E 99017 KS BACON 4PK            15.99
SUBTOTAL                       {S}
TAX                              1.84
TOTAL DUE                      {T}
ITEMS SOLD 5
""", [("KS CHICKEN BREAST",1,17.89),("KS PAPER TOWEL 12CT",1,22.99),("FRESH MOZZ 2LB",1,8.49),("ORG SALAD KIT",1,4.99),("KS BACON 4PK",1,15.99)], 1.84)

add("v06_walgreens_voided_item", """
Walgreens
Store #5521
SKITTLES BAG 14OZ           3.99
GREEK YOGURT 4PK            4.79
VOIDED ITEM  GREEK YOGURT 4PK  -4.79
PEANUT BUTTER CREAMY        3.49
DEL MONTE CORN CAN          1.29
OATMEAL INSTANT 10CT        3.79
Subtotal                   {S}
Total Tax                   0.00
Total                      {T}
""", [("SKITTLES BAG 14OZ",1,3.99),("PEANUT BUTTER CREAMY",1,3.49),("DEL MONTE CORN CAN",1,1.29),("OATMEAL INSTANT 10CT",1,3.79)], 0.0)

add("v07_99ranch_mixedcase_void_nomatch", """
99 Ranch Market
Napa Cabbage
  3.10 lb @ $0.69/lb        2.14
Fresh Shrimp 21/25
  1.05 lb @ $9.99/lb       10.49
Instant Ramen 5pk           4.25
Soy Milk Unsweetened        2.99
** VOID **  Mango Pudding  -2.49
Pocky Strawberry            1.79
Sub-total                  {S}
Total Tax                   0.00
Amount Due                 {T}
""", [("Napa Cabbage",3.10,2.14),("Fresh Shrimp 21/25",1.05,10.49),("Instant Ramen 5pk",1,4.25),("Soy Milk Unsweetened",1,2.99),("Pocky Strawberry",1,1.79)], -2.49)

add("v08_fiesta_multibuy_balance_due", """
FIESTA MART #14
TORTILLAS CORN 30CT         2.19
3 @ 2/$5.00 LIMES           7.50
AVOCADO HASS LG             1.25
POLLO ASADO 2LB            11.40
QUESO FRESCO 10OZ           3.99
CHORIZO LINK                4.49
SUBTOTAL                   {S}
TAX                         0.00
BALANCE DUE                {T}
Debit                      {T}
""", [("TORTILLAS CORN 30CT",1,2.19),("LIMES",3,7.50),("AVOCADO HASS LG",1,1.25),("POLLO ASADO 2LB",1,11.40),("QUESO FRESCO 10OZ",1,3.99),("CHORIZO LINK",1,4.49)], 0.0)

add("v09_campus_market_you_pay", """
Tigers' Corner Market - Dining Services
Meal Plan Swipe: *****7731
Grab&Go Chicken Wrap        6.25
Fuji Apple                  0.99
Chobani Greek Yogurt        1.89
Cold Brew 12oz              3.25
Trail Mix Single            1.79
Total Items: 5
You Pay                    {T}
""", [("Grab&Go Chicken Wrap",1,6.25),("Fuji Apple",1,0.99),("Chobani Greek Yogurt",1,1.89),("Cold Brew 12oz",1,3.25),("Trail Mix Single",1,1.79)], 0.0)

add("v10_coop_weighted_order_total", """
Riverbend Food Co-op
Member Owner #2208
Bulk Rolled Oats
  1.80 lb @ $1.49/lb        2.68
Local Honey 12oz           10.99
Organic Carrots 2lb         3.49
Co-op Basics Lentils        2.29
Member Discount 5%         -1.02
Sub Total                  {S}
Total Savings               1.02
Order Total                {T}
""", [("Bulk Rolled Oats",1.80,2.68),("Local Honey 12oz",1,10.99),("Organic Carrots 2lb",1,3.49),("Co-op Basics Lentils",1,2.29)], -1.02)

add("v11_kroger_void_first_then_items", """
KROGER #603
** VOID **  KRO ORANGE JUICE 52OZ  -3.99
KRO WHOLE MILK GAL          3.29
PRIVATE SELECT PASTA SAUCE  2.49
KRO BREAD WHEAT             1.79
ROTISSERIE CHICKEN          5.99
Total Savings               0.50
TOTAL TAX                   0.34
Balance Due                {T}
""", [("KRO WHOLE MILK GAL",1,3.29),("PRIVATE SELECT PASTA SAUCE",1,2.49),("KRO BREAD WHEAT",1,1.79),("ROTISSERIE CHICKEN",1,5.99)], -3.99 + 0.34)

add("v12_publix_mixedcase_total_due", """
Publix #0622
Sweet Baby Peppers 1lb      3.99
Ground Turkey 93/7          5.49
Barilla Penne 16oz          1.79
Cabot Cheddar Slices        3.29
Dozen Eggs Large            2.99
Savings Total               0.00
Tax                         0.00
Total Due                  {T}
""", [("Sweet Baby Peppers 1lb",1,3.99),("Ground Turkey 93/7",1,5.49),("Barilla Penne 16oz",1,1.79),("Cabot Cheddar Slices",1,3.29),("Dozen Eggs Large",1,2.99)], 0.0)

add("v13_sprouts_multibuy_void_between", """
SPROUTS #77
4 @ 2 for $5 ORG BANANAS    10.00
ORG BABY KALE 5OZ           3.99
VOID  ORG BABY KALE 5OZ    -3.99
ORG BABY KALE 5OZ           3.99
LACROIX 8PK                 4.99
FRESH PASTA RAVIOLI         5.49
Subtotal                   {S}
TOTAL SAVINGS               0.00
AMOUNT DUE                 {T}
""", [("ORG BANANAS",4,10.00),("ORG BABY KALE 5OZ",1,3.99),("LACROIX 8PK",1,4.99),("FRESH PASTA RAVIOLI",1,5.49)], 0.0)

add("v14_safeway_plain_order_total", """
SAFEWAY #2210
Deli Rotisserie Chicken     7.99
LUCERNE BUTTER 1LB          4.49
O ORGANICS APPLESAUCE       3.29
SIGNATURE FROZEN PEAS       1.99
GALA APPLES
  2.35 lb @ $1.79/lb        4.21
Item Total                 {S}
Sales Tax                   0.00
Total Tax                   0.00
Order Total                {T}
""", [("Deli Rotisserie Chicken",1,7.99),("LUCERNE BUTTER 1LB",1,4.49),("O ORGANICS APPLESAUCE",1,3.29),("SIGNATURE FROZEN PEAS",1,1.99),("GALA APPLES",2.35,4.21)], 0.0)

add("v15_walgreens_grocery_you_pay_multibuy", """
Walgreens #9087
Reg 3 Cashier Maria
2 @ 3/$4.00 GATORADE 20OZ   2.67
LAYS CLASSIC 8OZ            4.29
NATURE VALLEY BARS          3.49
BANANA                      0.35
Subtotal                   {S}
Total Savings               0.00
Total Tax                   0.27
You Pay                    {T}
""", [("GATORADE 20OZ",2,2.67),("LAYS CLASSIC 8OZ",1,4.29),("NATURE VALLEY BARS",1,3.49),("BANANA",1,0.35)], 0.27)

assert len(R) == 15
here = os.path.dirname(os.path.abspath(__file__)); out = os.path.join(here, "receipts_holdout_v2")
os.makedirs(out, exist_ok=True)
for name, text, lines, total in R:
    open(os.path.join(out, name + ".txt"), "w").write(text)
    json.dump({"receipt": name, "lines": lines, "total": total}, open(os.path.join(out, name + ".json"), "w"), indent=1)
print(len(R), "holdout v2 receipts")
