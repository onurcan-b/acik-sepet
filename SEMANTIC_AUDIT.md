# Açık Sepet v0.4 — Semantic Audit

Snapshot reviewed: **2026-09-11**

This audit is deliberately **review-only**. It does not change matching, panel membership, the published index, charts, or the README diagram.

## Executive summary

The deterministic/category-aware pipeline is technically healthy, but a few product types still have semantic scope problems that technical validation cannot detect.

### High-confidence issues

#### 1. `bread_white` — published as **Beyaz ekmek**

The active panel contains five rows, and the source category is `Somun Ekmek`. Current examples include:

- `Normal Kepekli Ekmek 200 Gr`
- `İHE Fındıklı Ve Üzümlü Ekmek 50 Gr`
- `İHE Organik Ekmek 500 Gr`
- `Uno Çok Tahıllı Ekmek 460 Gr`
- `Schar Pan Rustico Glutensiz Ekmek 250 Gr`

At least four are clearly specialty/non-ordinary breads. The cleanest methodological choices are either:

1. rename the type to **Somun ekmek** and explicitly accept the broader source-category scope, or
2. keep **Beyaz ekmek** and tighten the matching rules.

Do **not** silently tighten it in the existing series without checking coverage and continuity.

#### 2. `instant_coffee` — **Çözünebilir kahve**

Seven active SKUs were observed. Five are coffee premixes rather than plain soluble/granulated coffee:

- `Cafex Instant Mocha Kahve 18 Gr`
- `Nescafé Instant Mocha Kahve 17 Gr`
- `Nescafé 3'ü 1 Arada Sütlü Köpüklü Hazır Kahve 17 Gr`
- `Jacobs Gold Yoğun 3'ü 1 Arada Granül Kahve 18 Gr`
- `Starbucks Cappuccino Premium Kahve Karışımı 18 Gr`

Only two observed rows are clearly plain granulated coffee (`Carrefour Gold Kahve 100 Gr`, `Nescafé Gold Granül Kahve 100 Gr`). Since the type currently requires **6** SKUs, immediately excluding premixes would make the type non-viable. This should therefore remain an audit warning until the scope or minimum coverage policy is redesigned.

#### 3. `milk` — **İçme sütü**

The plain-milk panel contains:

- `Dost Laktozsuz Süt 1 Lt` — this concept already has its own `milk_lactosefree` type.
- `Dost İtalyan Karamelli Pastörize Süt 1 Lt` — flavored milk, economically distinct from ordinary milk.

This is the clearest example of a sibling-type leak. The audit now also checks for titles that satisfy another type's hard title rules within the same product group.

## Review-only heterogeneity

These are not necessarily wrong, but deserve explicit scope decisions:

- `vinegar`: white, balsamic, malt and specialty/"detox" vinegars share one type.
- `turkish_coffee`: ordinary, flavored and dibek variants share one type.
- `meatballs`: poultry and red-meat meatballs share one generic `Köfte` type.
- `olive_oil`: spray-format olive oil has a packaging premium very different from ordinary bottles.

Because Açık Sepet uses fixed-SKU price relatives, level differences are less damaging than they would be in a cheapest-item index. The main long-run risk is **replacement/bridging between economically different SKUs**.

## New automatic checks

`python -m acik_sepet.semantic_audit` now performs three review layers:

1. **Curated semantic rules** for known high-risk product types.
2. **Same-group title overlap**: a row is flagged when its title also satisfies another sibling type's hard title rules.
3. **Bridged replacement review**: every row with `generation > 0` is surfaced for manual semantic-equivalence review.

The command writes:

- `data/v0.4/semantic-audit.json`
- `data/v0.4/semantic-audit.md`

The audit intentionally exits successfully by default. `--fail-on-high` exists for a future point when the rules are mature enough to become a release gate.

## Recommended next methodology changes

Do these only after reviewing coverage impact:

1. Decide whether `bread_white` means **Beyaz ekmek** or broader **Somun ekmek**.
2. Split/exclude coffee premixes from plain instant coffee, but first solve the current lack of enough plain SKUs.
3. Exclude `laktozsuz` and flavored variants from plain `milk`; the dedicated lactose-free type already exists.
4. Review every bridged replacement before treating long-run panel continuity as fully trusted.

The current README diagram and published v0.4 index are intentionally unchanged by this audit.
