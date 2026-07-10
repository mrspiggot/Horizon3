# 11 — Model Reference (literature review)

The earlier drafts named models but never specified them. This document is the
literature review: for each model class the app must support, its **canonical
form**, **inputs** (with the derivative/context order each requires, per §10),
**outputs**, **what the output asserts**, **interpretation**, **why it is
insightful**, and **references**. This is the content that populates the Neo4j
model catalog (§06) and grounds the agent prompts (§12). It is a working
reference, not exhaustive — but it is specific enough to build from.

For each model, "insight" is stated as *the gap the model reveals* — because the
story is almost always the divergence between the model and the market/consensus.

---

## A. Central-bank policymaker

### A1 — Taylor rule and its variants
- **Form:** `i* = r* + π + 0.5(π − π*) + 0.5·(output gap)` (Taylor 1993). Variants:
  **1999 / "balanced-approach"** doubles the gap coefficient to 1.0;
  **first-difference** rule prescribes a *change* in the rate from activity/
  inflation changes (no r* level needed); **inertial** rule adds smoothing
  (partial adjustment to the prescription).
- **Inputs:** inflation **level and its change** (π and Δπ, core & headline), the
  inflation target π*, the **output gap** (a context/level construct), and **r\***
  (from A2). The first-difference variant is explicitly derivative-based.
- **Output:** a *prescribed* policy rate `i*` (one per variant).
- **Asserts:** "given this inflation and this slack, policy *should* be here."
- **Interpretation:** the **gap** between the prescription and the actual/market
  path is the policy-stance signal — restrictive if actual < prescription in an
  overheating regime, accommodative if above in a slack regime.
- **Insight:** the *dispersion across variants* is itself the story — the Fed's
  own Monetary Policy Report shows a fan of Taylor prescriptions; where the market
  sits within that fan is a positioning map.
- **Refs:** [Cleveland Fed simple-rules](https://www.clevelandfed.org/publications/economic-commentary/2016/ec-201601-the-natural-rate-of-interest-in-taylor-rules) ·
  [KC Fed "Beyond the Taylor Rule"](https://www.kansascityfed.org/documents/11203/Taylor_Rule.pdf)

### A2 — Natural rate of interest (r\*)
- **Form:** state-space / Kalman-filter estimation of an unobserved trend real
  rate (Laubach-Williams 2003; Holston-Laubach-Williams 2017). Lubik-Matthes is a
  VAR-based alternative.
- **Inputs:** real GDP (trend & gap), core inflation, the real policy rate — all
  as **trends and deviations** (context constructs), estimated recursively.
- **Output:** a slow-moving r\* estimate (HLW ~0.7%, Lubik-Matthes ~1.5%, Fed
  staff ~1.0–1.2%).
- **Asserts:** "the neutral real rate is here" — the anchor for A1.
- **Interpretation:** policy is restrictive when the real rate > r\*, easy when <.
  Not observable — model-dependent, so *always show which estimate*.
- **Insight:** the range across estimators bounds "how tight is policy, really."
- **Refs:** [Dallas Fed r\*](https://www.dallasfed.org/research/economics/2023/0703) ·
  [Cleveland Fed](https://www.clevelandfed.org/publications/economic-commentary/2016/ec-201601-the-natural-rate-of-interest-in-taylor-rules)

---

## B. Rates traders (macro & relative value)

### B1 — Affine term-structure / term-premium (ACM, Kim-Wright)
- **Form:** multi-factor affine dynamic term-structure model. **ACM**
  (Adrian-Crump-Moench, NY Fed) estimates it via a **three-step linear
  regression** on zero-coupon yields; **Kim-Wright** (Fed Board) is a 3-factor
  arbitrage-free model.
- **Inputs:** the zero-coupon yield curve (daily); pricing factors are the
  curve's own level/slope/curvature (PCA-like context).
- **Output:** decomposition of each yield into an **expectations** component and a
  **term premium** component.
- **Asserts:** "of the 10y yield, this much is expected future short rates and
  this much is the risk premium for holding duration."
- **Interpretation:** a selloff driven by *term premium* (supply, uncertainty) is
  a different trade from one driven by *expectations* (repricing the Fed path).
- **Insight:** the term-premium series is a positioning signal (rich/cheap
  duration); the decomposition tells you *why* rates moved.
- **Refs:** [NY Fed ACM / Treasury Term Premia](https://libertystreeteconomics.newyorkfed.org/2014/05/treasury-term-premia-1961-present/) ·
  [BIS term premia](https://www.bis.org/publ/qtrpdf/r_qt1809h.pdf) ·
  [Fed Kim-Wright robustness](https://www.federalreserve.gov/econres/notes/feds-notes/robustness-of-long-maturity-term-premium-estimates-20170403.html)

### B2 — Curve factor model (Nelson-Siegel / PCA)
- **Form:** reduce the curve to 3 factors — **level, slope, curvature** (PCA) or
  the Nelson-Siegel functional form.
- **Inputs:** the full curve (levels) and its **changes** (factor moves).
- **Output:** factor loadings + fair-value residuals per tenor.
- **Asserts:** "this tenor is rich/cheap relative to the fitted curve."
- **Interpretation / insight:** RV signals (butterflies, spreads); a large
  curvature move is a different macro signal from a slope move.

### B3 — Carry & roll-down
- **Form:** expected return of a rates position absent yield change = carry
  (yield) + roll-down (sliding down a static curve).
- **Inputs:** the curve **shape** (level + slope), funding.
- **Output:** expected carry per position/tenor.
- **Asserts:** "you are paid this much to hold, if nothing moves."
- **Insight:** carry vs the fair-value/term-premium signal is the trade-selection
  frame for a macro rates book.

---

## C. Credit investor

### C1 — Merton structural model / distance-to-default
- **Form:** equity is a **European call option on the firm's assets** (Merton
  1974); default occurs if asset value < debt at maturity.
- **Inputs:** asset value & **asset volatility** (inferred from equity value/vol),
  debt (default point), horizon, risk-free rate. Equity vol is a level+change
  input.
- **Output:** **distance-to-default** (number of asset-vol standard deviations to
  the default point) → probability of default and an implied **credit spread**.
- **Asserts:** "the firm is DD standard deviations from default; the fair spread
  is X."
- **Interpretation:** model spread vs market spread = rich/cheap credit; DD
  *falling* (its derivative) is an early-warning signal.
- **Insight:** derives a spread **without bond prices** — useful where market data
  are thin; the basis (model − market) is the trade.
- **Refs:** [Merton structural model](https://ryanoconnellfinance.com/merton-structural-credit-model/) ·
  [MATLAB Merton DD](https://www.mathworks.com/help/risk/default-probability-using-the-merton-model-for-structural-credit-risk.html)

---

## D. Equity / multi-asset PM

### D1 — Gordon growth / dividend discount & the equity risk premium
- **Form:** `P = D₁ / (r − g)`; rearranged, **ERP ≈ dividend yield + g − long
  government yield**. Cost of equity via CAPM `r = r_f + β·ERP`.
- **Inputs:** dividend/earnings yield (level), expected **growth g** (a
  derivative/expectation), the long bond yield (level), real rates.
- **Output:** intrinsic value / implied ERP.
- **Asserts:** "equities offer this premium over bonds for this growth."
- **Interpretation:** the **Fed-model** comparison (earnings yield vs bond yield)
  says rich/cheap vs bonds. *Caveat to encode:* as `r → g`, `(r−g) → 0` and value
  explodes — the model has *broken down*, not found infinite value; the agent must
  flag this, not report it.
- **Insight:** ERP vs its history and vs real rates is the allocation signal.
- **Refs:** [Gordon ERP](https://breakingdownfinance.com/finance-topics/equity-valuation/gordon-equity-risk-premium-model/) ·
  [Damodaran DDM](https://pages.stern.nyu.edu/~adamodar/pdfiles/ddm.pdf)

---

## E. FX trader

### E1 — Equilibrium exchange-rate models (PPP / BEER / FEER) and UIP/carry
- **Form:** **PPP** (long-run price-level parity); **BEER** (behavioural
  equilibrium — a reduced-form regression on fundamentals); **FEER** (the rate
  consistent with a sustainable current account); **UIP** (expected FX move offsets
  the rate differential).
- **Inputs:** rate **differentials** and inflation **differentials** (derivative/
  relative constructs), terms of trade, current account, productivity.
- **Output:** an equilibrium/fair-value exchange rate; UIP-implied forward path.
- **Asserts:** "the currency is X% mis-aligned vs fundamentals."
- **Interpretation / insight:** UIP **fails empirically** — high-yielders don't
  depreciate as much as the differential implies — and *that failure is the carry
  trade*. The model's value is often in where reality *deviates* from it.
- **Refs:** [CFA parity conditions](https://analystprep.com/study-notes/cfa-level-2/international-parity-conditions/) ·
  [Handbook: currency fair-value models](https://onlinelibrary.wiley.com/doi/10.1002/9781118445785.ch11)

---

## F. Commodity analyst

### F1 — Theory of storage / convenience yield
- **Form:** `F = S + storage cost − convenience yield` (Kaldor 1939, Working 1949,
  Brennan 1958). Working's storage supply curve maps the price of storage against
  inventory.
- **Inputs:** spot, **inventory level and its change** (the convenience yield is a
  strongly non-linear function of inventory), storage cost, financing rate.
- **Output:** the fair futures curve shape — **contango** (ample inventory) vs
  **backwardation** (scarcity → high convenience yield).
- **Asserts:** "the curve should be in backwardation/contango given inventories."
- **Interpretation / insight:** curve shape vs inventory trend is the positioning
  signal; a **short-run scarcity shock** steepens backwardation non-linearly.
- **Refs:** [Theory of storage / convenience yield](https://www.equicurious.com/learn/derivatives/futures-and-forwards/commodity-futures-storage-and-convenience-yield) ·
  [NBER commodity futures returns](https://www.nber.org/system/files/working_papers/w13249/w13249.pdf) ·
  [IMF: curves & inventories under scarcity](https://www.imf.org/external/pubs/ft/wp/2010/wp10222.pdf)

---

## G. Volatility trader

### G1 — Variance risk premium (VRP)
- **Form:** `VRP = implied variance − expected realized variance`; VIX
  approximates 30-day expected realized vol nonparametrically; affine models fit
  SPX + VIX jointly.
- **Inputs:** the vol surface / VIX (implied, level+change) and **realized vol**
  (a derivative-of-price construct).
- **Output:** the premium paid for volatility insurance; a term structure of VRP.
- **Asserts:** "options are pricing this much more variance than is likely to
  realise."
- **Interpretation / insight:** a large positive VRP is compensation for selling
  insurance; VRP vs its history is the vol-positioning signal; the *sign and
  change* of VRP flag regime shifts.
- **Refs:** [Carr-Wu Variance Risk Premia](https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf) ·
  [Fed: variance risk premia & returns](https://www.federalreserve.gov/pubs/feds/2007/200711/200711pap.pdf)

---

## H. Economist / forecaster

### H1 — Nowcasting (dynamic factor model)
- **Form:** a **dynamic factor model** extracts a common factor from many
  higher-frequency series; **GDPNow** combines it with **bridge equations** and
  **BVARs** across 13 GDP subcomponents.
- **Inputs:** the **changes** in ISM, construction, vehicle sales, trade,
  employment, IP, housing starts, PPI/CPI — fundamentally a derivative-driven
  model (§10).
- **Output:** a running estimate of current-quarter real GDP that updates with
  each release.
- **Asserts:** "given the data in so far, growth is tracking X%."
- **Interpretation / insight:** the nowcast vs consensus, and its *revision path*
  (its own derivative) as data arrive, is the surprise/positioning signal.
- **Refs:** [Atlanta Fed GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow/explainer)

### H2 — Surprise vs expectations
- **Form:** `surprise = actual − expected`, where "expected" is market-implied
  (OIS/Kalshi) or survey consensus.
- **Inputs:** the print, and the pre-event expectation (already produced by UMD's
  expectations layer).
- **Output:** a signed, scaled surprise; a surprise index across releases.
- **Asserts:** "the data beat/missed what was priced."
- **Insight:** the surprise, not the level, moves markets; this is the "context vs
  expectations" order of §10 as a first-class series.

---

## I. Event / prediction-market trader

### I1 — Implied distribution + calibration / bias-correction
- **Form:** convert contract prices to an implied probability distribution;
  correct for known Kalshi biases; compare to a model fair value.
- **Inputs:** contract mids/orderbooks, the underlying macro model's output.
- **Output:** a calibrated implied distribution and an **edge** (model − market).
- **Asserts:** "the crowd prices X%; the model says Y%."
- **Insight:** the edge and the calibration receipt (past implied vs realised) are
  the trade and the credibility. *Already implemented in UMD* (`pm_service`,
  `kalshi_implied_distribution`, `kalshi_bias_correction`).

---

## How this reference is used

Each model above becomes a `ModelSpecification` node (§06) carrying its form,
its `ModelInput` tuples (with the §10 derivative/context orders), its outputs,
and — critically for narration — a **`asserts` / `interpretation` field** so the
narrator agent (§12) can explain *what the number means* without inventing it.
The `IMPLEMENTED_BY` edge points at the UMD `analysis/` function (present for
~55% today; the remainder are the build list in §07/§09). This reference is the
seed content; extending it from ArXiv/central-bank literature is the ongoing model
curation pipeline.
