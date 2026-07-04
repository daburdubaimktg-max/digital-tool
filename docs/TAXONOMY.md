# Taxonomy & ID Conventions

This is the governance layer that plugs three structural gaps in the marketing
data: missing business outcomes, missing markets (Egypt & Turkey), and the
disconnect between influencer content and the paid campaigns that boost it.
Every new data submission is validated against these rules by
`tools/validate_submission.py` before it enters the warehouse.

## 1. Controlled vocabularies (`vocab/`)

| File | Contents | Rule |
|---|---|---|
| `markets.csv` | 28 markets → region → cluster, incl. **Egypt** and **Turkey** (status `onboarding` until their first data lands) | `market` values in any submission must match exactly |
| `brands.csv` | 32 brands → 3-letter brand code → category | brand names must match exactly; new brands are added here first |
| `platforms.csv` | platforms → 2-letter code → family (Meta, TikTok, Google, Retail Media…) | no free-typed platform names (`facebook` → `Facebook`) |
| `enums.csv` | objectives, influencer tiers, creative languages, asset sources, outcome metrics | kills the `Mega`/`MEGA`/`Macro ` and `english`/`English` problem |

**One owner.** New values enter these files via PR — never free-typed into a
tracker. The validator rejects anything not in the lists.

## 2. Campaign IDs

Free-text campaign names (570 unique strings across 1,037 rows today) become
structured IDs:

```
FY27-Q2-VEHO-EGY-TT-AWR-001
│    │   │    │   │  │   └─ sequence number within the combination
│    │   │    │   │  └───── objective code (AWR awareness, VIE views, TRF traffic, ENG engagement, CNV conversions)
│    │   │    │   └──────── platform code (vocab/platforms.csv)
│    │   │    └──────────── market code (vocab/markets.csv)
│    │   └───────────────── brand code (vocab/brands.csv)
│    └───────────────────── fiscal quarter
└────────────────────────── fiscal year (Apr–Mar)
```

The human-readable campaign name stays as a separate field; the ID is what
joins spend, creative, influencer boosts, and outcomes.

## 3. Asset IDs — the influencer ↔ paid bridge

Today only 16 of 483 influencer activations have boosting rights recorded, and
nothing links an influencer asset to the paid campaign that amplified it — so
true blended cost per asset (fee + boost) is uncomputable.

Every piece of creative gets an ID at creation time:

```
AST-FY27-VEHO-0001
```

- The **influencer tracker** (`templates/influencer_activation_v2.csv`) records
  `asset_id`, plus `boost_campaign_id` and `boost_spend_aed` when boosted.
- The **paid media tracker** (`templates/paid_media_submission.csv`) records
  `asset_id` and the asset's `hook_description` and `creative_language`.
- Blended asset economics, whitelisted-UGC vs brand-creative performance, and
  "which hooks work" all become single SQL joins.

## 4. Outcomes — the missing half of "what works"

No sales, conversion, or revenue signal exists in any tracker today.
`templates/outcomes_monthly.csv` is the minimal monthly feed, at
brand × market × month grain, metric as an enum:

| metric | source |
|---|---|
| `sell_out_value_usd` / `sell_out_units` | distributor sell-out / Nielsen |
| `market_share_pct` | retail audit |
| `ecom_revenue_usd` | Amazon / noon / DTC |
| `search_index` | Google Trends — **automated**, `tools/trends_proxy.py` |
| `distribution_pct` | field sales |

Start with whichever column finance/regional teams can fill; `search_index`
flows automatically from day one and serves as the demand proxy until harder
data arrives.

## 5. Egypt & Turkey onboarding

Both markets are in `vocab/markets.csv` (status `onboarding`). Local teams /
agencies submit monthly via `templates/paid_media_submission.csv`; the
validator gives them an exact, actionable error list, so no cleanup lands on
the central team. First accepted file flips the market's status to `active`.

## 6. Validation gate

```
python3 tools/validate_submission.py <file.csv> --type paid|influencer|outcomes
```

Checks: required columns present, vocab/enum membership, date parseability,
non-negative numerics, spend-vs-impressions sanity (CPM bounds), and campaign
/asset ID format. Exit code 0 = load-ready; otherwise a row-by-row error
report is printed for the submitter.
