#!/usr/bin/env python3
"""Summarise Gemini usage from the backend's `app.gemini.usage` log lines.

    docker compose logs api | python scripts/gemini_cost.py
    python scripts/gemini_cost.py api.log --price gemini-2.5-flash=0.30,2.50

Line format (written by backend/app/services/gemini.py):
    ... app.gemini.usage gemini_usage model=M purpose=P input_tokens=N output_tokens=N
        total_tokens=N latency_ms=N status=ok|error      (N may be "null")
Other lines are ignored.
"""
import argparse
import re
import sys
from collections import defaultdict

# Paid-tier standard prices, USD per 1M (input, output) tokens; output includes thinking tokens.
# Verified 2026-10-10 on https://ai.google.dev/gemini-api/docs/pricing. gemini-3.8-flash and
# 3.6-flash prices double on 2027-01-01 (to 1.50 / 7.50): re-check before relying on any figure,
# or override with --price / --default-price.
PRICES = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
}
DEFAULT_PRICE = (0.75, 3.75)  # used for models missing from PRICES (= gemini-3.8-flash)

_LINE = re.compile(r"gemini_usage\s+(.*)")
_KV = re.compile(r"(\w+)=(\S+)")


def _int(v):
    return int(v) if v and v.isdigit() else None


def parse(lines):
    for line in lines:
        m = _LINE.search(line)
        if not m:
            continue
        kv = dict(_KV.findall(m.group(1)))
        if "model" in kv:
            yield kv


def _pair(text):
    a, b = text.split(",")
    return float(a), float(b)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="log file (default: stdin)")
    ap.add_argument("--price", action="append", default=[], metavar="MODEL=IN,OUT",
                    help="override USD per 1M input,output tokens for a model (repeatable)")
    ap.add_argument("--default-price", metavar="IN,OUT", help="price for models not in the table")
    args = ap.parse_args()

    prices = dict(PRICES)
    for spec in args.price:
        model, _, pair = spec.partition("=")
        prices[model] = _pair(pair)
    default = _pair(args.default_price) if args.default_price else DEFAULT_PRICE

    rows = defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # calls, errors, in, out, total, unknown_usage
    src = open(args.file) if args.file else sys.stdin
    for kv in parse(src):
        r = rows[(kv["model"], kv.get("purpose", "?"))]
        r[0] += 1
        r[1] += kv.get("status") == "error"
        tin, tout, ttl = _int(kv.get("input_tokens")), _int(kv.get("output_tokens")), _int(kv.get("total_tokens"))
        if tin is None and tout is None:
            r[5] += 1
        r[2] += tin or 0
        r[3] += tout or 0
        r[4] += ttl if ttl is not None else (tin or 0) + (tout or 0)

    if not rows:
        print("No gemini_usage lines found.")
        return
    hdr = f"{'model':<26}{'purpose':<12}{'calls':>6}{'err':>5}{'in_tok':>11}{'out_tok':>11}{'total_tok':>12}{'cost_usd':>11}"
    print(hdr)
    print("-" * len(hdr))
    tot = [0, 0, 0, 0, 0, 0]
    tot_cost = 0.0
    for (model, purpose), r in sorted(rows.items()):
        pin, pout = prices.get(model, default)
        cost = (r[2] * pin + r[3] * pout) / 1e6
        tot_cost += cost
        tot = [a + b for a, b in zip(tot, r)]
        note = "" if model in prices else "  (default price)"
        note += f"  ({r[5]} call(s) without usage)" if r[5] else ""
        print(f"{model:<26}{purpose:<12}{r[0]:>6}{r[1]:>5}{r[2]:>11,}{r[3]:>11,}{r[4]:>12,}{cost:>11.4f}{note}")
    print("-" * len(hdr))
    print(f"{'TOTAL':<38}{tot[0]:>6}{tot[1]:>5}{tot[2]:>11,}{tot[3]:>11,}{tot[4]:>12,}{tot_cost:>11.4f}")
    print("Prices are estimates; verify against Google's pricing page.")


if __name__ == "__main__":
    main()
