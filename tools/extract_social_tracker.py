#!/usr/bin/env python3
"""Extract the Master Social Media Tracker workbook into a tidy dataset.

Unpivots the wide month-per-column sheets (Instagram (2), Tiktok, Hobby EA)
into one long-format table:

    platform, brand, username, category, region, owner, snapshot_date,
    followers, suspect

- "38k"/"1.2M" strings and comma numbers are normalized to integers.
- Text month labels ("Feb", "Mar'26", "June") are mapped to real dates.
- `owner` = dabur | competitor, from username/brand patterns.
- `suspect` = True when a snapshot moves >50% vs the previous one for the
  same page (almost always a data-entry error, e.g. garnierarabia 301k -> 33k).

Usage:
    python3 tools/extract_social_tracker.py <tracker.xlsx> [-o data/social_followers.csv]
"""
import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

TEXT_MONTHS = {
    "feb": datetime(2026, 2, 24), "june": datetime(2026, 6, 26),
    "mar'26": datetime(2026, 3, 1), "apr'26": datetime(2026, 4, 1),
    "may'26": datetime(2026, 5, 1), "june'26": datetime(2026, 6, 1),
}

DABUR_PATTERNS = re.compile(
    r"dabur|vatika|fem(arabia|__africa)|dermoviva|herbolene|hobby|"
    r"orsoliveoil|orshaircare|princessamira|hydra\.curls", re.I)

SHEETS = [
    ("Instagram (2)", "Instagram", "Username"),
    ("Tiktok", "TikTok", "URLs"),
    ("Hobby EA", None, "URLs"),  # platform inferred per row from the URL
]


def clean_count(v):
    if pd.isna(v):
        return None
    s = str(v).strip().replace(",", "").replace(" ", "")
    if not s or s in ("-", "nan", "NaN"):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)([kKmM])?$", s)
    if not m:
        return None
    n = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6}.get((m.group(2) or "").lower(), 1)
    return int(n * mult)


def col_to_date(col):
    if isinstance(col, datetime):
        return col
    if isinstance(col, pd.Timestamp):
        return col.to_pydatetime()
    key = str(col).strip().lower()
    return TEXT_MONTHS.get(key)


def username_from_url(url):
    if pd.isna(url):
        return None
    m = re.search(r"(?:instagram\.com|tiktok\.com)/@?([\w\.\-_]+)", str(url))
    return m.group(1).rstrip("/") if m else None


def platform_from_url(url):
    s = str(url)
    if "tiktok.com" in s:
        return "TikTok"
    if "instagram.com" in s:
        return "Instagram"
    return None


def extract(xlsx: Path) -> pd.DataFrame:
    frames = []
    for sheet, platform, handle_col in SHEETS:
        df = pd.read_excel(xlsx, sheet_name=sheet)
        df.columns = [c if not isinstance(c, str) else c.strip().rstrip("\\") for c in df.columns]
        id_cols = [c for c in df.columns if isinstance(c, str) and col_to_date(c) is None]
        date_cols = [c for c in df.columns if col_to_date(c) is not None]

        for _, row in df.iterrows():
            brand = row.get("Brand")
            if pd.isna(brand):
                continue
            url = row.get("Instagram Url", row.get("URLs"))
            username = row.get("Username") if "Username" in df.columns else username_from_url(url)
            plat = platform or platform_from_url(url)
            if plat is None:
                continue
            handle = str(username or brand).strip()
            owner = "dabur" if DABUR_PATTERNS.search(handle + " " + str(brand)) else "competitor"
            for c in date_cols:
                followers = clean_count(row[c])
                if followers is None:
                    continue
                frames.append({
                    "platform": plat,
                    "brand": str(brand).strip(),
                    "username": username,
                    "category": row.get("Category"),
                    "region": row.get("Region"),
                    "owner": owner,
                    "snapshot_date": col_to_date(c).date(),
                    "followers": followers,
                })

    out = pd.DataFrame(frames).sort_values(["platform", "username", "brand", "snapshot_date"])
    out = out.drop_duplicates(subset=["platform", "username", "brand", "snapshot_date"], keep="last")

    # flag >50% month-over-month jumps as suspect data entry
    key = out["platform"].astype(str) + "|" + out["username"].astype(str) + "|" + out["brand"]
    prev = out.groupby(key)["followers"].shift(1)
    ratio = out["followers"] / prev
    out["suspect"] = ((ratio < 0.5) | (ratio > 2.0)) & prev.notna()
    return out.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workbook", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("data/social_followers.csv"))
    args = ap.parse_args()

    df = extract(args.workbook)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    own = df[df.owner == "dabur"]
    print(f"Wrote {len(df):,} snapshots → {args.out}")
    print(f"Pages: {df.groupby('platform')['username'].nunique().to_dict()}"
          f" | Dabur-owned pages: {own.groupby('platform')['username'].nunique().to_dict()}")
    print(f"Date range: {df.snapshot_date.min()} → {df.snapshot_date.max()}")
    print(f"Suspect snapshots flagged: {int(df.suspect.sum())}")


if __name__ == "__main__":
    main()
