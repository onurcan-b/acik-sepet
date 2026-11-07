# ECB-inspired repricing experiment — Açık Sepet

Research branch: **research/ecb-repricing**. This **does not redefine or rewrite** the published v0.4 index or its protected history.

Reference: Osbat, Höynck, Maglione & Wieland (ECB, 2 November 2026),
[Catching the repricing wave: insights from daily online supermarket prices](https://www.ecb.europa.eu/press/blog/date/2026/html/ecb.blog20261102~871cc494e2.en.html).

## Indicators

- **Extensive margin:** share of matched product × store normalized-price quotes rising, falling, or unchanged from the previous month-end. A 0.1% tolerance ignores rounding noise. The denominator is comparable quotes, **not** all products in the basket; it is published alongside category coverage. Missing categories are never silently treated as unchanged.
- **Intensive margin:** average nonzero increase and decrease, separately; also publish the mean signed change across all matched quotes.
- **Breadth:** percentage of the **total configured food-category weight** whose categories have at least 10% increasing quotes (minimum five matched quotes per represented category). A missing category contributes no breadth but remains in the total food-weight denominator.
- **Early warning:** a provisional month-to-date estimate recalculated for each observed day, plus its difference versus the **same elapsed calendar day in the preceding month** (e.g., November 6 versus October 6), when available. Unmatched periods are never compared.

Outputs: [latest report](output/latest.md), [chart](output/repricing.svg), [daily CSV](output/daily_repricing.csv), [category CSV](output/category_repricing.csv), [JSON](output/latest.json), [source-quality audit](output/quality.json), [food breadth chart](output/breadth.svg).

## Comparison and cleaning rules

1. Compare an identical type_id, *actual* product_key, source/depot ID, normalized unit, and pack size. **Do not** compare different SKUs merely because they occupy the same v0.4 continuity slot_id; changing the store sample or pack size is not a genuine price-change observation.
2. Use source-level api_unit_price from source_observations. Fall back to aggregated unit prices only when a legacy snapshot has precisely one identifiable depot; multi-store legacy aggregates are excluded.
3. Require source timestamp no more than one day older than the snapshot date. Previous month-end reference price may come from any of the last eight calendar days of that month; a current quote is from today or yesterday. Skip ratios below 0.5× or above 2× as possible data errors.
4. Suppress *sale-like V-shaped temporary reductions* of ≥3% that reverse within seven days to within 1% of the original price. This pattern does **not** prove a promotion, and discounts lasting longer or still active at the latest observation remain included. A sensitivity analysis with actual promotion flags is necessary. This can bias frequency and magnitude in either direction.
5. Weight category-level frequencies using existing Açık Sepet research category weights, not EU HICP or Turkish official CPI expenditure weights. Include categories only with at least five comparable quotes; publish basket-weight coverage separately. The headline includes **nonfood** products; separate food-only increase/decrease frequencies are shown alongside it for closer comparison to ECB food-sector estimates.

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

## Validation and known limitations (7 November 2026)

**Research only; do not interpret these as validated price-setting rates or inflation forecasts.**

Independent spot-check of raw stored snapshots from 30 September, 1/6/31 October and 1/6 November found **no source-unit-price inconsistencies or duplicate depot-SKU quote keys** in those particular files. This does not prove that the full collection pipeline is free from errors. One identical product/store/size matched quote between 31 October and 6 November changed its textual product title; no other title changes were found among 1,684 spot-checked matched records.

Between 31 October and 6 November, **253 of 1,672 matched quotes inside the ±50%/+100% input bounds moved by at least 20% (15.1%)**. For these 1,672 quotes, the shares of >20% absolute movements were 28.3% among Migros quotes, 23.1% among Carrefour quotes, and 7.7% among BİM quotes. Four prices approximately doubled, and several rises were close to 66.7%. These changes can represent actual promotion expiry, temporary pricing, source distortions, or less common genuine adjustments. The raw source quotes do not identify promotion status reliably; it would be misleading to call the full average price change a structural repricing magnitude.

The main category-weight coverage measure is based on **only five matched store–SKU quotations per category**, not a coverage ratio against all desired products, regions, chains, or unique items. The basket is not nationally representative.

Current analysis compares month-end reference quotes with latest fresh day/day-before quotes. This is **not a full reconstruction of ECB DPD's country/product panel and promotion methodology**. We do not identify every within-month repricing event or claim an ECB-equivalent frequency. Prices are primarily collected around specific Turkish depot locations.

The hourly supermarket collection pipeline on **main** is not modified by the research script. It only consumes pre-existing saved main snapshots. For source quality, inspect [the original collection diagnostics](../../data/v0.4/quality.json), the current research [quality audit](output/quality.json), and reproducible tests.

Outstanding before publication: manually verify 20–30 extreme price events with retailer/source history, evaluate discount removal sensitivity, audit all snapshot dates and missing products, and validate out-of-sample forecast performance against Turkish official food inflation. No causal or predictive claim is justified yet.
