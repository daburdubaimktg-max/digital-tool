#!/usr/bin/env python3
"""Google Trends demand proxy — automated `search_index` outcome feed.

Until sell-out / market-share data is flowing, this gives every brand ×
market a monthly demand signal for free. Output rows match
templates/outcomes_monthly.csv and pass the validation gate.

Setup (run wherever it can reach Google — laptop or a monthly cron):
    pip install pytrends
Usage:
    python3 tools/trends_proxy.py --fy "FY 26-27" --month July \
        --out outcomes_search_$(date +%Y%m).csv
"""
import argparse
import csv
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Search terms per brand — what consumers actually type, not internal names.
BRAND_TERMS = {
    "Vatika Hair Oil": "vatika hair oil",
    "Vatika EHO": "vatika enriched hair oil",
    "Vatika Shampoo": "vatika shampoo",
    "Dabur Amla": "dabur amla",
    "Dermoviva": "dermoviva",
    "Dabur Miswak": "dabur miswak",
    "DHTP": "dabur herbal toothpaste",
    "FEM": "fem cream",
    "Dabur Honitus": "honitus",
    "Hobby Shampoo": "hobby şampuan",
    "ORS": "ors hair",
    "Real Juices": "real juice",
}

# Google Trends geo codes per market (subset — extend from vocab/markets.csv).
MARKET_GEO = {
    "KSA": "SA", "UAE": "AE", "Kuwait": "KW", "Qatar": "QA", "Bahrain": "BH",
    "Oman": "OM", "Jordan": "JO", "Iraq": "IQ", "Egypt": "EG", "Turkey": "TR",
    "Morocco": "MA", "Algeria": "DZ", "Tunisia": "TN", "Libya": "LY",
    "Uzbekistan": "UZ", "Kazakhstan": "KZ", "Kyrgyzstan": "KG",
    "Azerbaijan": "AZ", "Ethiopia": "ET", "Kenya": "KE", "Tanzania": "TZ",
    "Zambia": "ZM", "South Africa": "ZA", "Singapore": "SG", "Malaysia": "MY",
    "Australia": "AU",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fy", required=True, help='e.g. "FY 26-27"')
    ap.add_argument("--month", required=True, help="e.g. July")
    ap.add_argument("--out", type=Path, default=Path("outcomes_search_index.csv"))
    ap.add_argument("--sleep", type=float, default=2.0,
                    help="seconds between requests (Trends rate-limits hard)")
    args = ap.parse_args()

    from pytrends.request import TrendReq  # pip install pytrends
    py = TrendReq(hl="en-US", tz=240)

    rows = []
    for brand, term in BRAND_TERMS.items():
        for market, geo in MARKET_GEO.items():
            try:
                py.build_payload([term], timeframe="today 3-m", geo=geo)
                df = py.interest_over_time()
                if df.empty:
                    continue
                # mean of the most recent ~30 daily/weekly points
                idx = round(float(df[term].tail(30).mean()), 1)
                rows.append({
                    "fiscal_year": args.fy, "month": args.month,
                    "brand": brand, "market": market,
                    "metric": "search_index", "value": idx, "currency": "",
                    "source": "Google Trends (auto)",
                    "notes": f"term='{term}' geo={geo} timeframe=today 3-m",
                })
                print(f"  {brand} × {market}: {idx}")
            except Exception as exc:  # rate limits, no data, etc.
                print(f"  skip {brand} × {market}: {exc}")
            time.sleep(args.sleep)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["fiscal_year", "month", "brand",
                                           "market", "metric", "value",
                                           "currency", "source", "notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows → {args.out}")
    print("Validate: python3 tools/validate_submission.py "
          f"{args.out} --type outcomes")


if __name__ == "__main__":
    main()
