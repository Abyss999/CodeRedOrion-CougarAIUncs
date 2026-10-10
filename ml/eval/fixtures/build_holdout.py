#!/usr/bin/env python
"""Generates the BLIND holdout receipts in fixtures/receipts_holdout/. Same GT conventions as
build_receipts.py (items only; price = line total charged; total = amount paid). Voided items:
neither the original line nor the VOID line is an item, and the total excludes them.
Never tune the parser against these; they exist to detect overfitting to receipts/."""
import json, os
R = []
def add(name, text, lines, total, adj):
    s = round(sum(l[2] for l in lines) + adj, 2)
    assert abs(s - total) < 0.005, f"{name}: {s} != {total}"
    R.append((name, text.strip("\n") + "\n", [{"name": n, "quantity": q, "price": p} for n, q, p in lines], total))

add("h01_traderjoes", """
TRADER JOE'S
Store #082 - Palo Alto
Cage Free Large Eggs                 $3.99
Unexpected Cheddar Cheese            $4.49
Organic Baby Spinach                 $2.99
Everything But The Bagel Seasoning   $2.49
Fresh Atlantic Salmon Fillet         $9.87
Items in Transaction: 5
Balance to pay                      $23.83
""", [("Cage Free Large Eggs",1,3.99),("Unexpected Cheddar Cheese",1,4.49),("Organic Baby Spinach",1,2.99),("Everything But The Bagel Seasoning",1,2.49),("Fresh Atlantic Salmon Fillet",1,9.87)], 23.83, 0)

add("h02_heb_bogo", """
H-E-B
SLC ORG CHKN STRIPS 12OZ   6.49
BUY 1 GET 1 FREE
  ORG CHKN STRIPS 12OZ     6.49
  BOGO SAVINGS            -6.49
BLUEBONNET BUTTER 1LB      3.98
TX PEACHES 2 LB            4.98
Subtotal                  15.45
Tax                        0.00
Total                     15.45
Combo Loyalty Savings      6.49
""", [("SLC ORG CHKN STRIPS 12OZ",1,6.49),("ORG CHKN STRIPS 12OZ",1,6.49),("BLUEBONNET BUTTER 1LB",1,3.98),("TX PEACHES 2 LB",1,4.98)], 15.45, -6.49)

add("h03_aldi_qty", """
ALDI #44
2 x Brioche Buns 8ct      2.38
1 x Honeycrisp Apples 3lb 4.99
3 x Greek Yogurt Vanilla  2.67
SUBTOTAL                 10.04
TOTAL DUE               10.04
""", [("Brioche Buns 8ct",2,2.38),("Honeycrisp Apples 3lb",1,4.99),("Greek Yogurt Vanilla",3,2.67)], 10.04, 0)

add("h04_target_circle", """
TARGET
Good & Gather Organic Milk      4.19
Good & Gather Baby Carrots      1.89
Market Pantry Spaghetti         1.29
Up&Up Paper Towels  T           7.99
   Target Circle 10% Off       -0.80
SUBTOTAL                       14.56
T = CA TAX 8.75%                0.70
TOTAL                          15.26
AMEX ENDING 1005               15.26
""", [("Good & Gather Organic Milk",1,4.19),("Good & Gather Baby Carrots",1,1.89),("Market Pantry Spaghetti",1,1.29),("Up&Up Paper Towels",1,7.99)], 15.26, -0.80+0.70)

add("h05_wholefoods_prime", """
WHOLE FOODS MARKET
BLUEBERRIES ORG PINT        5.99
   Prime Member Deal       -1.00
SOURDOUGH BATARD            4.49
WILD ARUGULA
   0.62 lb @ 7.99/lb        4.95
GRASS FED GROUND BEEF 1LB  10.99
SUBTOTAL                   25.42
TAX                         0.00
TOTAL                      25.42
""", [("BLUEBERRIES ORG PINT",1,5.99),("SOURDOUGH BATARD",1,4.49),("WILD ARUGULA",0.62,4.95),("GRASS FED GROUND BEEF 1LB",1,10.99)], 25.42, -1.00)

add("h06_bodega", """
Joe's Deli & Grocery
Egg sandwich       4.50
Coffee large       1.75
Banana             0.50
Milk quart         2.25
Bread Wonder       3.49
                -------
TOTAL             12.49
Cash              20.00
Change             7.51
Thank u!
""", [("Egg sandwich",1,4.50),("Coffee large",1,1.75),("Banana",1,0.50),("Milk quart",1,2.25),("Bread Wonder",1,3.49)], 12.49, 0)

add("h07_asian_mixedcase", """
Great Wall Supermarket
Fresh Bok Choy
  2.15 lb @ $1.29/lb        2.77
Silken Tofu 16oz            1.99
Lee Kum Kee Oyster Sauce    3.49
Pork Belly Sliced
  1.40 lb @ $5.99/lb        8.39
Jasmine Rice 10lb          14.99
Sub-total                  31.63
Total                      31.63
""", [("Fresh Bok Choy",2.15,2.77),("Silken Tofu 16oz",1,1.99),("Lee Kum Kee Oyster Sauce",1,3.49),("Pork Belly Sliced",1.40,8.39),("Jasmine Rice 10lb",1,14.99)], 31.63, 0)

add("h08_farmers_market", """
Sunny Acres Farm Stand
Tomatoes heirloom 2lb   $6.00
Sweet corn x6          $4.50
Honey jar               $9.00
Eggs dozen              $5.50
   thank you!!
Total                  $25.00
""", [("Tomatoes heirloom 2lb",1,6.00),("Sweet corn",6,4.50),("Honey jar",1,9.00),("Eggs dozen",1,5.50)], 25.00, 0)

add("h09_multipage", """
FRESH & EASY MARKET #19
Page 1 of 2
CHEDDAR CHEESE BLOCK       3.99
TURKEY SLICES 9OZ          4.29
HUMMUS CLASSIC             2.99
-- continued --

FRESH & EASY MARKET #19
Page 2 of 2
RED GRAPES SEEDLESS        3.77
LUNCHMEAT HAM 8OZ          3.49
SUBTOTAL                  18.53
TAX                        0.00
TOTAL                     18.53
""", [("CHEDDAR CHEESE BLOCK",1,3.99),("TURKEY SLICES 9OZ",1,4.29),("HUMMUS CLASSIC",1,2.99),("RED GRAPES SEEDLESS",1,3.77),("LUNCHMEAT HAM 8OZ",1,3.49)], 18.53, 0)

add("h10_voided", """
VONS
LG AVOCADOS 4CT           5.99
ORGANIC KALE              2.49
VOID  ORGANIC KALE       -2.49
CAGE FREE EGGS 18         6.49
BUTTER SALTED 1LB         4.79
*** ITEM VOIDED ABOVE ***
SUBTOTAL                 17.27
TAX                       0.00
TOTAL                    17.27
""", [("LG AVOCADOS 4CT",1,5.99),("CAGE FREE EGGS 18",1,6.49),("BUTTER SALTED 1LB",1,4.79)], 17.27, 0)

add("h11_loyalty_savings_total_tax", """
RALPHS
Card# ******4821
ORANGE JUICE NFC 52OZ       4.99
   Card Savings            -1.50
STRAWBERRIES 1LB            3.99
ROTISSERIE CHICKEN          6.99
PEPSI 12PK  T               6.49
TOTAL SAVINGS               1.50
SALES TAX                   0.55
BALANCE DUE                21.51
""", [("ORANGE JUICE NFC 52OZ",1,4.99),("STRAWBERRIES 1LB",1,3.99),("ROTISSERIE CHICKEN",1,6.99),("PEPSI 12PK",1,6.49)], 21.51, -1.50+0.55)

add("h12_whole_numbers_and_long", """
SAFEWAY #1590   
03/22/2026
2 PK GALA APPLES           3.00
3 @ 2/$5.00 GREEN ONIONS   7.50
RED BELL PEPPER
  0.85 lb @ $2.49/lb       2.12
BEEF CHUCK ROAST           12.40
COTTAGE CHEESE 16OZ         2.79
FROZEN BROCCOLI 12OZ        1.50
TOTAL                      29.31
""", [("2 PK GALA APPLES",1,3.00),("GREEN ONIONS",3,7.50),("RED BELL PEPPER",0.85,2.12),("BEEF CHUCK ROAST",1,12.40),("COTTAGE CHEESE 16OZ",1,2.79),("FROZEN BROCCOLI 12OZ",1,1.50)], 29.31, 0)

here = os.path.dirname(os.path.abspath(__file__)); out = os.path.join(here, "receipts_holdout")
os.makedirs(out, exist_ok=True)
for name, text, lines, total in R:
    open(os.path.join(out, name + ".txt"), "w").write(text)
    json.dump({"receipt": name, "lines": lines, "total": total}, open(os.path.join(out, name + ".json"), "w"), indent=1)
print(len(R), "holdout receipts")
