#!/usr/bin/env python3
"""Validation gate for marketing data submissions.

Usage:
    python3 tools/validate_submission.py <file.csv|xlsx> --type paid|influencer|outcomes

Exit code 0 means the file is load-ready; 1 means it was rejected and a
row-by-row error report was printed. Uses only the standard library so any
regional team can run it without installing anything (xlsx needs pandas).
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VOCAB = REPO / "vocab"

CAMPAIGN_ID = re.compile(r"^FY\d{2}-Q[1-4]-[A-Z]{2,4}-[A-Z]{3}-[A-Z]{2}-[A-Z]{3}-\d{3}$")
ASSET_ID = re.compile(r"^AST-FY\d{2}-[A-Z]{2,4}-\d{4}$")

REQUIRED = {
    "paid": [
        "fiscal_year", "month", "quarter", "campaign_id", "campaign_name",
        "platform", "objective", "brand", "market", "start_date", "end_date",
        "budget_usd", "spend_usd", "impressions",
    ],
    "influencer": [
        "fiscal_year", "quarter", "month", "brand", "influencer_name",
        "platform", "asset_type", "influencer_tier", "market", "cost_aed",
        "asset_id",
    ],
    "outcomes": [
        "fiscal_year", "month", "brand", "market", "metric", "value", "source",
    ],
}

NUMERIC_NON_NEGATIVE = {
    "paid": ["budget_usd", "spend_usd", "spend_aed", "impressions",
             "video_views", "link_clicks", "reach", "engagements"],
    "influencer": ["followers", "cost_aed", "views", "interactions",
                   "boost_spend_aed"],
    "outcomes": ["value"],
}

CPM_BOUNDS_USD = (0.05, 150.0)  # sanity range across all our markets/platforms


def load_vocab():
    def col(fname, field):
        with open(VOCAB / fname, newline="", encoding="utf-8-sig") as fh:
            return {row[field].strip() for row in csv.DictReader(fh)}

    enums = {}
    with open(VOCAB / "enums.csv", newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            enums.setdefault(row["field"], set()).add(row["value"])
    return {
        "market": col("markets.csv", "market"),
        "brand": col("brands.csv", "brand"),
        "platform": col("platforms.csv", "platform"),
        "objective": enums.get("objective", set()),
        "influencer_tier": enums.get("influencer_tier", set()),
        "creative_language": enums.get("creative_language", set()),
        "metric": enums.get("outcome_metric", set()),
    }


def read_rows(path):
    if path.suffix.lower() in (".xlsx", ".xls"):
        import pandas as pd  # only needed for Excel submissions
        df = pd.read_excel(path)
        df.columns = [str(c).strip() for c in df.columns]
        return df.columns.tolist(), df.fillna("").astype(str).to_dict("records")
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols = [c.strip() for c in reader.fieldnames or []]
        return cols, [dict(r) for r in reader]


def is_number(v):
    try:
        float(str(v).replace(",", ""))
        return True
    except ValueError:
        return False


def parse_date(v):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(v).strip()[:10], fmt)
        except ValueError:
            continue
    return None


def validate(path, ftype):
    vocab = load_vocab()
    cols, rows = read_rows(path)
    errors = []

    missing = [c for c in REQUIRED[ftype] if c not in cols]
    if missing:
        errors.append(f"HEADER: missing required columns: {', '.join(missing)}")
        return errors  # column errors make row checks meaningless

    vocab_checks = {
        "market": vocab["market"], "brand": vocab["brand"],
        "platform": vocab["platform"], "objective": vocab["objective"],
        "influencer_tier": vocab["influencer_tier"],
        "creative_language": vocab["creative_language"],
        "metric": vocab["metric"],
    }

    for i, row in enumerate(rows, start=2):  # 1-based + header line
        get = lambda c: str(row.get(c, "")).strip()

        for c in REQUIRED[ftype]:
            if not get(c):
                errors.append(f"row {i}: '{c}' is empty")

        for c, allowed in vocab_checks.items():
            v = get(c)
            if c in cols and v and allowed and v not in allowed:
                hint = next((a for a in allowed if a.lower() == v.lower()), None)
                fix = f" (did you mean '{hint}'?)" if hint else ""
                errors.append(f"row {i}: '{c}' value '{v}' not in vocab{fix}")

        for c in NUMERIC_NON_NEGATIVE[ftype]:
            v = get(c)
            if c in cols and v:
                if not is_number(v):
                    errors.append(f"row {i}: '{c}' = '{v}' is not a number")
                elif float(v.replace(",", "")) < 0:
                    errors.append(f"row {i}: '{c}' = '{v}' is negative")

        if not re.match(r"^FY\s?\d{2}\s?-\s?\d{2}$", get("fiscal_year")):
            errors.append(f"row {i}: fiscal_year '{get('fiscal_year')}' must look like 'FY 26-27'")

        if ftype == "paid":
            if get("campaign_id") and not CAMPAIGN_ID.match(get("campaign_id")):
                errors.append(f"row {i}: campaign_id '{get('campaign_id')}' does not match FYnn-Qn-BRAND-MKT-PL-OBJ-nnn")
            if get("asset_id") and not ASSET_ID.match(get("asset_id")):
                errors.append(f"row {i}: asset_id '{get('asset_id')}' does not match AST-FYnn-BRAND-nnnn")
            sd, ed = parse_date(get("start_date")), parse_date(get("end_date"))
            if get("start_date") and not sd:
                errors.append(f"row {i}: start_date '{get('start_date')}' unparseable (use YYYY-MM-DD)")
            if get("end_date") and not ed:
                errors.append(f"row {i}: end_date '{get('end_date')}' unparseable (use YYYY-MM-DD)")
            if sd and ed and sd > ed:
                errors.append(f"row {i}: start_date after end_date")
            if is_number(get("spend_usd")) and is_number(get("impressions")):
                spend, imps = float(get("spend_usd").replace(",", "")), float(get("impressions").replace(",", ""))
                if imps > 0 and spend > 0:
                    cpm = spend / imps * 1000
                    lo, hi = CPM_BOUNDS_USD
                    if not lo <= cpm <= hi:
                        errors.append(f"row {i}: implied CPM ${cpm:,.2f} outside sanity range ${lo}-${hi} — check spend/impressions units")

        if ftype == "influencer":
            if get("asset_id") and not ASSET_ID.match(get("asset_id")):
                errors.append(f"row {i}: asset_id '{get('asset_id')}' does not match AST-FYnn-BRAND-nnnn")
            if get("boosting_rights").lower() == "yes" and not get("boost_campaign_id"):
                errors.append(f"row {i}: boosting_rights=Yes but boost_campaign_id is empty — the influencer/paid link is the point")
            if get("boost_campaign_id") and not CAMPAIGN_ID.match(get("boost_campaign_id")):
                errors.append(f"row {i}: boost_campaign_id '{get('boost_campaign_id')}' does not match campaign ID format")

    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", type=Path)
    ap.add_argument("--type", required=True, choices=["paid", "influencer", "outcomes"])
    args = ap.parse_args()

    if not args.file.exists():
        print(f"REJECTED: file not found: {args.file}")
        sys.exit(1)

    errors = validate(args.file, args.type)
    if errors:
        print(f"REJECTED: {args.file.name} — {len(errors)} issue(s):\n")
        for e in errors[:200]:
            print(f"  - {e}")
        if len(errors) > 200:
            print(f"  ... and {len(errors) - 200} more")
        sys.exit(1)
    print(f"OK: {args.file.name} is load-ready.")
    sys.exit(0)


if __name__ == "__main__":
    main()
