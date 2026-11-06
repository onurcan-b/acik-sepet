# ECB-inspired repricing experiment — Açık Sepet

Research branch: **research/ecb-repricing**. This **does not redefine or rewrite** the published v0.4 index or its protected history.

Reference: Osbat, Höynck, Maglione & Wieland (ECB, 2 November 2026),
[Catching the repricing wave: insights from daily online supermarket prices](https://www.ecb.europa.eu/press/blog/date/2026/html/ecb.blog20261102~871cc494e2.en.html).

## Indicators

- **Extensive margin:** share of matched product × store normalized-price quotes rising, falling, or unchanged from the previous month-end. A 0.1% tolerance ignores rounding noise. The denominator is comparable quotes, **not** all products in the basket; it is published alongside category coverage. Missing categories are never silently treated as unchanged.
- **Intensive margin:** average nonzero increase and decrease, separately; also publish the mean signed change across all matched quotes.
- **Breadth:** percentage of the **total configured food-category weight** whose categories have at least 10% increasing quotes (minimum five matched quotes per represented category). A missing category contributes no breadth but remains in the total food-weight denominator.
- **Early warning:** a provisional month-to-date estimate recalculated for each observed day, plus its up-frequency difference in percentage points versus the previous completed month's last estimate when available.

Outputs: [latest report](output/latest.md), [chart](output/repricing.svg), [daily CSV](output/daily_repricing.csv), [category CSV](output/category_repricing.csv), [JSON](output/latest.json).

## Comparison and cleaning rules

1. Compare an identical type_id, *actual* product_key, source/depot ID, normalized unit, and pack size. **Do not** compare different SKUs merely because they occupy the same v0.4 continuity slot_id; changing the store sample or pack size is not a genuine price-change observation.
2. Use source-level api_unit_price from source_observations. Fall back to aggregated unit prices only when a legacy snapshot has precisely one identifiable depot; multi-store legacy aggregates are excluded.
3. Require source timestamp no more than one day older than the snapshot date. Previous month-end reference price may come from any of the last eight calendar days of that month; a current quote is from today or yesterday. Skip ratios below 0.5× or above 2× as possible data errors.
4. Omit *confirmed* temporary discounts of ≥3% that reverse within seven days to within 1% of the original price. Sales still active at the latest observation cannot be recognized yet; **current-month estimates may therefore include temporary promotions**.
5. Weight category-level frequencies using existing Açık Sepet research category weights, not EU HICP or Turkish official CPI expenditure weights. Include categories only with at least five comparable quotes; publish basket-weight coverage separately.

This is **not a reproduction of the ECB's Daily Price Dataset**, nor is Açık Sepet an official TÜİK price index. The ECB uses its own classification and aggregation, a more extensive product/retailer panel, official HICP weights, and a fuller promotional-price treatment. The current experiment does **not** use AI classification, because Açık Sepet already maintains explicit product-type and COICOP-like category mappings. An AI classifier should only be added after a labelled matching benchmark demonstrates an improvement.

A rise in repricing frequency is an **indicator of pricing behavior**, not a validated forecast of future TÜFE. Further validation should compare leading indicators against out-of-sample next-month inflation and measure stability across retailers, categories, and source freshness.

## Offline schedule and rate limits

The [research Action](https://github.com/onurcan-b/acik-sepet/actions/workflows/ecb-repricing.yml) runs at **09:47 UTC daily**, staggered from the main collection schedule **05:17, 13:17 and 21:17 UTC**. GitHub may delay scheduled runs.

**No additional supermarket API calls:** the scheduled job checks out this branch, fetches only the existing v0.4 snapshots and category configuration from origin/main via local Git, runs tests, calculates the indicators, and commits generated research output **only** to this branch. It never updates main, and the existing collector remains unchanged.

GitHub only executes schedule triggers for workflows on the repository's default branch. Consequently, the small scheduler workflow file lives on main, while the implementation and daily research outputs live here.

Reproduce locally with:
    python -m acik_sepet.ecb_repricing --snapshots-dir data/v0.4/snapshots --categories config/categories.json --output-dir research/ecb/output

Run tests with:
    pytest -q tests/test_ecb_repricing.py
