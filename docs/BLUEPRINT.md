# Dabur Digital Intelligence Brain — System Blueprint

**Goal:** one system where anyone on the team asks a plain-English question —
*"What was our TikTok CPM in KSA vs Unilever's last quarter?"*, *"Which hooks
worked for Vatika EHO in Arabic?"*, *"Where are we underspending vs competition?"*
— and gets a correct, cited answer drawn from performance marketing, influencer
marketing, social trackers, competitive intelligence (Spyglass), and internal
communications.

---

## 1. The right architecture (and why NOT a fine-tuned LLM)

Training/fine-tuning a "low level LLM" on the metrics themselves is the wrong
tool: numbers baked into model weights go stale the day new data arrives, the
model will confidently hallucinate figures, and retraining per month is slow and
expensive.

The proven pattern for this problem is an **agentic analytics stack**:

```
                      ┌─────────────────────────────────────────────┐
 QUESTION  ──────────▶│  Claude agent (the "brain")                 │──────▶ ANSWER
 (Slack / WhatsApp /  │  tools: run_sql · search_knowledge ·        │        (numbers + charts
  web chat)           │         get_benchmarks · make_chart         │         + cited sources)
                      └────────────┬───────────────┬────────────────┘
                                   │               │
                     ┌─────────────▼────┐   ┌──────▼──────────────────┐
                     │  WAREHOUSE       │   │  KNOWLEDGE BASE (vector)│
                     │  (facts & dims,  │   │  creative hooks, briefs,│
                     │  semantic views, │   │  internal comms, comp.  │
                     │  metric defs)    │   │  ad transcripts         │
                     └─────────────▲────┘   └──────▲──────────────────┘
                                   │               │
                     ┌─────────────┴───────────────┴────────────────┐
                     │  INGESTION & NORMALIZATION PIPELINE          │
                     │  Excel/Sheets · Meta/TikTok/YT APIs ·        │
                     │  Spyglass exports · Slack/email/decks        │
                     └──────────────────────────────────────────────┘
```

The LLM never stores the data — it **queries** governed data live. That makes
answers always-current, auditable (every answer cites the rows it used), and
cheap to maintain.

---

## 2. What exists today (audit of the 4 master workbooks)

| Source | Grain | Coverage | Key fields |
|---|---|---|---|
| **Master Performance Marketing FY24-26** — source-of-truth tabs: **`Combined Data FY 23-26`** + **`Africa Campaigns`** only (pivot tabs used solely as cross-check references, all other tabs ignored) | campaign × platform × market × month (1,037 + 47 rows) | FY23-26 · 8 regions · 26 markets (Combined: GCC→CIS→North Africa→Australia; Africa tab adds South Africa, Tanzania, Zambia, Kenya) · 32 brands · 10 platforms · ~$2.73M spend | Budget/Spend (USD+AED), Impressions, Views (2s/3s/6s/15s), Clicks, CPM/CPC/CPV, CTR, Hook Rate (TikTok & IG), VTR, VV 25–100%, Reach, Frequency, TG |
| **Master Influencer Dashboard FY23-26** | activation (483 rows) | FY23-26 · GCC + beyond | Influencer, tier (Nano→Mega), KOL type, platform, asset type, followers, cost AED, views, watch time, interactions, CPF/CPV/CPI, ER%, boosting rights, content links |
| **Master Social Media Tracker FY23-26** | page × month follower series | Own + competitor pages (Sunsilk, Garnier, Vaseline…), IG + TikTok, Dec'22→Jun'26 | follower counts, page URLs, region |
| **TikTok Competition Landscape FY25-26** (Spyglass-style) | competitor × product × month, UAE/KSA | Unilever 25.8M AED · L'Oréal 17.8M · Kenvue 14.0M · P&G 4.2M · **Dabur 1.5M** (180d TikTok) | spends, impressions, views, CPM, creative language, product, parent company |

### Data-quality findings that block "just point an LLM at the Excel"

- **Inconsistent controlled vocabularies:** `Mega`/`MEGA`/`Macro ` (trailing
  space) are three different groups today; `english` vs `English`; `Skin Care`
  vs `Skin care`.
- **Mixed date encodings:** Excel serials (`44934`) sitting next to datetimes in
  the same column.
- **Wide/pivot-shaped sheets:** the social tracker stores months as ~40 columns;
  Creative Analysis has 4 pivot blocks pasted side-by-side with `Unnamed:` gaps.
- **Duplicated column blocks** in the competition sheet (same data twice per row).
- **Schema drift between the two source tabs:** `Africa Campaigns` uses
  `Spends(USD)` vs Combined's `Spends (USD)`, lacks Fiscal Year / Budget /
  Start–End dates / Engagements, and lowercases platforms (`facebook`). The
  loader maps both into the same `fact_paid_media` shape.
- **No creative registry:** hook *rate* is tracked, but hook *content* (the
  actual opening device, script, format) is not — so "which hooks work?" is
  currently unanswerable by any system.

These are all fixable mechanically in the ingestion layer — and they are exactly
why the pipeline is step one.

---

## 3. Canonical data model (star schema)

**Fact tables**

| Table | Grain |
|---|---|
| `fact_paid_media` | campaign × platform × market × month — spend, impressions, views ladder, clicks, reach, engagement |
| `fact_influencer_activation` | one influencer post/activation — cost, views, interactions, watch time |
| `fact_social_followers` | page × platform × month — followers (own + competitors), unpivoted from the wide tracker |
| `fact_competitor_media` | competitor brand × product × market × month — spend, impressions, views, CPM (Spyglass) |

**Dimension tables**

| Table | Contents |
|---|---|
| `dim_brand` | brand → hero product line → category → parent company (ours *and* competitors', so SOV joins work) |
| `dim_market` | market → region → cluster (GCC, MENA ex-GCC, North Africa, CIS/Central Asia — Uzbekistan/Kazakhstan/Kyrgyzstan/Azerbaijan, Sub-Saharan — Ethiopia/Kenya/Tanzania/Zambia, South Africa, Asia — SG/MY, Australia/Fiji) |
| `dim_platform` | platform → family (Meta = FB+IG, TikTok, YouTube, programmatic, local: Koora/Shahid) |
| `dim_creative` | **the new creative/hook registry**: creative ID, hook text & type, language, format, duration, hero product, asset link |
| `dim_influencer` | influencer → tier, KOL specialty, country, profile links, follower history |
| `dim_date` | Dabur fiscal calendar (FY Apr–Mar, Q1–Q4, H1/H2) |
| `dim_currency` | AED⇄USD (fixed peg) + any local currencies |

**Semantic layer on top:** every metric defined *once* in SQL views —
CPM, CPV, CPF, CPI, CTR, VTR, hook rate, ER%, SOV, reach % — plus a
`benchmarks` table (platform benchmarks like the 5.5% VTR benchmark already in
the Creative Analysis sheet). The agent only queries these views, never raw
sheets, so numbers are consistent no matter who asks.

**Engine:** start with **DuckDB** (single file, zero infra, ridiculously fast,
reads Excel/CSV natively) → graduate to Postgres or BigQuery when multiple
writers/team access demand it. dbt for the transform layer when it matures.

---

## 4. Ingestion workflow

1. **Master workbooks (now):** Python loaders per workbook that unpivot wide
   sheets, fix serial dates, normalize vocabularies against the controlled
   lists, and load to the warehouse. Idempotent — re-drop the file, re-run.
   For the Performance workbook only `Combined Data FY 23-26` and
   `Africa Campaigns` are ingested; the pivot tabs (`Pivot FY 23-26`, `PT_*`,
   `All Campaign Pivot`) are used as reconciliation checks — loader totals must
   match the pivots before a load is accepted — and every other tab is ignored.
2. **Monthly drops (ongoing):** a landing folder (Drive/SharePoint). New file →
   validation gate (schema check, vocab check, spend-total sanity vs last
   month) → auto-load → Slack summary of what changed. Bad rows are quarantined
   with a reason, never silently dropped.
3. **Platform APIs (phase 2):** Meta Marketing API, TikTok Ads API, YouTube/DV360
   — replaces manual data dumps for the biggest platforms, gives daily grain.
4. **Spyglass:** export competitor spend/creative data on a schedule (CSV export
   from the app, or its API if the plan includes one) → `fact_competitor_media`
   + competitor creatives (with language, product, hook) into the knowledge base.
5. **Internal & competitor communications:** campaign briefs, PPT decks, Slack
   threads, agency emails, competitor ad transcripts → chunked, embedded, stored
   in the vector knowledge base with metadata (brand, market, date, source).
6. **Creative/hook registry discipline:** every new ad creative gets a row in
   `dim_creative` at trafficking time (hook text, language, format, hero
   product). For historical creatives, an LLM pass over content links +
   Spyglass creative library backfills tags automatically.

---

## 5. The agent layer

A Claude-powered agent with four tools:

- **`run_sql`** — text-to-SQL against the semantic views only (read-only role).
  The schema + metric definitions + fiscal calendar rules live in its system
  prompt, so "last quarter" resolves to the right fiscal quarter.
- **`search_knowledge`** — semantic search over briefs, comms, creative hooks,
  competitor ad copy.
- **`get_benchmarks`** — platform/category benchmarks for "is this good?"
  questions.
- **`make_chart`** — renders trend/comparison charts into the reply.

**Guardrails:** read-only DB role; every numeric answer must cite table + filter
used; "I don't have data for X" beats a guess; PII-free by design.

**Surfaces (in order of effort):**
1. **Slack/WhatsApp bot** — where the team already lives; fastest to ship.
2. **Web chat + dashboard** (this repo, `digital-tool`) — chat pane plus the
   always-on views: spend vs plan, SOV vs competitors, CPM league table,
   influencer ROI board.
3. **Scheduled digests** — weekly auto-generated "what worked / what didn't"
   brief per region; monthly competitive SOV alert (e.g., "Unilever TikTok spend
   in KSA up 40% MoM").

---

## 6. What it will answer (already verified against your data)

- *"Where is media cheapest for us?"* → North Africa $0.41 CPM, Iraq/Emerging
  $0.53, GCC $1.76, Australia $8.77 (all-FY, USD).
- *"Which platform is most efficient?"* → TikTok $0.78 / Instagram $0.66 CPM at
  scale; programmatic $15.65 — 20× GCC social CPMs; Koora at $61.62 needs a
  hard look.
- *"Which influencer tier gives the best cost-per-view?"* → Mega 0.015 AED CPV
  and Micro 0.018 beat Macro 0.028 — Macro is 269 of 449 activations, i.e., the
  biggest optimization lever in the influencer budget.
- *"How outgunned are we on TikTok in UAE/KSA?"* → Dabur Amla 1.5M AED vs
  Unilever 25.8M, L'Oréal 17.8M over 180 days → ~2% SOV in tracked categories.
- *"What language should we boost in?"* → competitor spend splits ~56% Arabic /
  44% English — comparable per-market splits for our own spends come free once
  creative language joins `fact_paid_media`.

Plus, once the creative registry and comms ingestion land: hook-level
win/loss analysis, "what did we say internally before the campaigns that
over-delivered", and competitor messaging timelines.

---

## 7. Roadmap

| Phase | Timeline | Deliverable |
|---|---|---|
| **0 — Foundation** | Week 1 | Controlled vocabularies (brand/market/platform/tier lists), fiscal calendar, this blueprint signed off |
| **1 — Working brain (MVP)** | Weeks 2–3 | ETL for the 4 master workbooks → DuckDB star schema → Claude Q&A agent on Slack/CLI. Answers ~80% of the questions above |
| **2 — Competitive + creative depth** | Weeks 4–6 | Spyglass pipeline, creative/hook registry + LLM auto-tagging, comms ingestion, benchmarks, monthly drop automation with validation gate |
| **3 — Product** | Weeks 7–10 | Web app (chat + dashboards) in this repo, scheduled digests, anomaly alerts, platform API connectors, budget-planning copilot |

**Running cost:** near-zero infra in phase 1 (DuckDB is a file); phase 3 at
team scale ≈ $200–500/mo (hosting + Claude API + embeddings). No model
training required, ever.

---

## 8. Gap remediation — shipped in this repo

Three structural gaps identified in review are now plugged with working
machinery (see `docs/TAXONOMY.md` for the full rules):

1. **No outcome data** → `fact_outcomes` feed at brand × market × month grain.
   Template: `templates/outcomes_monthly.csv` (sell-out value/units, market
   share, e-commerce revenue, distribution). `tools/trends_proxy.py` automates
   a Google Trends `search_index` per brand × market from day one as the
   demand proxy until harder data flows.
2. **Egypt & Turkey missing** → both added to `vocab/markets.csv` (status
   `onboarding`). Local teams/agencies submit via
   `templates/paid_media_submission.csv`; the validation gate returns exact
   row-level errors so no cleanup lands centrally.
3. **Influencer ↔ paid disconnect** → shared `asset_id`
   (`AST-FY27-VEHO-0001`) recorded in both trackers, plus `boost_campaign_id`
   and `boost_spend_aed` in the influencer tracker
   (`templates/influencer_activation_v2.csv`). Blended asset cost (fee +
   boost) and UGC-vs-brand-creative comparisons become single joins.

Supporting both: structured campaign IDs
(`FY27-Q2-VEHO-EGY-TT-AWR-001`) replace 570 free-text names, and
`tools/validate_submission.py` enforces all of it — controlled vocabularies,
ID formats, date parseability, CPM sanity bounds — before anything enters the
warehouse.

## 9. Operating model (the part that makes it stick)

- **One taxonomy owner** — new brand/market/hook values enter through the
  controlled list, not free-typed into Excel.
- **Validation gate over goodwill** — files that fail schema/vocab checks bounce
  back with a precise error, so the warehouse never rots.
- **Creative tagging at trafficking time** — 2 minutes per creative buys
  permanent hook-level analytics.
- **The agent cites everything** — trust is the product; an uncited number is a
  bug.
