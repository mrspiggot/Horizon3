# CBOE volatility data — coverage & where to use it

**Status (2026-07-15):** 19 CBOE volatility indices are now ingested into UMD — backfilled
(deep history) and auto-collected daily by `unified_market_data/providers/cboe.py`. This doc
maps where that data adds signal across the persona × model matrix. It is a **roadmap**: the
data is in place; the models below are proposed, prioritized, not yet built.

## The data now available (source `cboe`, daily)

| Group | Series | History | Measures |
|---|---|---|---|
| S&P term structure | VIX1D, VIX9D, VIX, VIX3M, VIX6M, VIX1Y | 2022 / 2011 / 1990 / 2009 / 2008 / 2007 | 1-day → 1-year implied vol |
| Second-order / tail | VVIX, SKEW | 2006 / 1990 | vol-of-vol; option-implied crash risk |
| US equity indices | VXN, RVX, VXD | 2009 | Nasdaq-100 / Russell 2000 / Dow vol |
| Ex-US / EM | VXEEM, VXFXI, VXEWZ | 2011 | EM / China / Brazil equity vol |
| Commodity | OVX, GVZ, VXSLV, VXGDX | 2009 / 2011 | crude / gold / silver / gold-miners vol |
| Rates | VXTLT | 2004 | 20y+ Treasury bond vol |

Discontinued (backfill-only if ever needed, not daily): VXO (2021), TYVIX (2023), EVZ (2025).

Today only VIX/VIX9D/VIX3M/VIX6M are wired into models — all `volatility_trader`, all S&P.
**Five personas (equity PM, commodity, treasurer, rates, credit) have zero implied-vol input.**
The biggest opportunity is cross-asset, not more S&P.

## A. Enhancements to existing models (cheapest wins)

1. **`vol_term_structure` ← add VIX1D + VIX1Y** — the model claims the "entire VIX term structure"
   but stops at 9d–6m; the two ends make it a true 1-day→1-year six-tenor curve (front-fear vs
   long-end legs). *Needs: extend `vol_analytics.vol_term` args + catalog inputs.*
2. **`variance_risk_premium` ← add VIX1D + VVIX** — day-of event premium; VVIX distinguishes
   "VRP fat because vol is high" from "fat because convexity is bid".
3. **`return_distribution` ← add SKEW** — pairs option-**implied** left-tail price with the current
   realized skew/kurtosis; enables an implied-vs-realized-skew gap (tradable put richness).
4. **`garch_volatility` ← add VVIX** — a large `implied−GARCH` premium with low VVIX is a clean
   harvest; with high VVIX it's a trap. One input + one chart row.
5. **`financial_conditions` ← overlay VIX** on the NFCI risk subindex (daily tradable analogue).
6. **`gold_real_yield` ← add GVZ** — confirm the gold dislocation signal with gold implied vol.

## B. New models (highest strategic value — light up vol-blind personas)

1. **`cross_asset_vol_surface`** (equity PM) ⭐ — z-score VIX/VXN/RVX/VXTLT/OVX/GVZ/VXEEM vs own
   history → one regime heatmap: is stress single-asset or systemic? First true cross-asset risk map.
2. **`smallcap_risk_appetite`** (equity PM) ⭐ — the RVX−VIX spread as a clean risk-on/off gauge
   (small-cap fear vs large-cap). Trivial computation, deep history.
3. **`skew_crash_probability`** (vol trader) ⭐ — convert SKEW into an implied 2σ-left-tail
   probability, compare to realized tail frequency → an *ex-ante* crash-risk premium.
4. **`commodity_vol_stress`** (commodity) ⭐ — OVX vs GVZ/VXSLV: oil-supply-shock vs broad macro-fear;
   the commodity persona's first forward-looking risk input.
5. **`vvix_vol_risk_premium`** (vol trader) — VVIX vs realized vol-of-VIX: prices the hedge on the
   VRP harvest (convexity richness).
6. **`em_vol_dispersion`** (equity PM / new EM persona) — VXEEM/VXFXI/VXEWZ minus DM baseline as a
   capital-flight gauge; opens EM coverage (currently none).

## C. Coverage gaps this fills

- **Treasurer + rates trader → first rates-vol input (VXTLT).** Add to `funding_cost` as a
  duration-timing gauge; a candidate standalone `rates_vol` model overlays `term_premium_surface`.
  Largest net-new gain: two decision-makers, zero current vol, deep history (2004+).
- **Commodity analyst → first forward-looking risk input (OVX/GVZ/VXSLV/VXGDX).**
- **Equity PM → first direct market-vol inputs** (was NFCI + FF89 + gold only).
- **EM/China/Brazil (VXEEM/VXFXI/VXEWZ) → no consumer today** — entirely new coverage.
- **VVIX + SKEW → owned-but-unused** higher-order structure for the vol persona.

**Build order:** A1 + A3 are the cheapest high-value wins; B1, B2, B3 and the VXTLT treasurer/rates
gap-fill are the highest strategic value (they light up personas that are currently vol-blind).
Each new model needs an implementing function in `unified_market_data.analysis.*` plus a catalog YAML.
