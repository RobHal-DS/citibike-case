# CitiBike × AXA: Pay-per-Ride Micro-Insurance

A dynamic accident insurance that activates per CitiBike trip, with premiums calculated from actual trip risk — powered by CitiBike trip data and NYPD collision data.

---

## The Opportunity

NYC records ~6,700 bicycle-involved crashes per year (NYPD data), yet CitiBike offers no built-in accident coverage. Annual insurance policies don't fit ad-hoc bike-share usage — especially for casual riders (tourists, infrequent users) who have zero coverage. AXA can close this gap with a **pay-per-ride micro-insurance** that activates automatically at trip start, with premiums from $0.50 to $2.00 based on real risk factors.

## Data

Two public datasets drive the model: **CitiBike trip data** (~9.3M trips in 2025 — timestamps, station coordinates, rider type) and **NYPD Motor Vehicle Collisions** (~6,700 bicycle-involved crashes with geocoded locations, injury counts, and vehicle types). Details: [NB01 — CitiBike EDA](notebooks/01_eda_citibike.ipynb), [NB02 — NYPD EDA](notebooks/02_eda_nypd.ipynb).

## Risk Model

Every trip gets a risk score from three multiplicative factors, each derived from data:

```
trip_risk = station_risk × temporal_multiplier × rider_multiplier
```

### Station Risk

Each CitiBike station is scored by the number and severity of NYPD bicycle crashes within a 250m buffer — roughly one minute of riding. The composite score weights accident frequency (how many crashes) and severity (cyclist injuries per crash). This produces a right-skewed distribution: most stations are low-risk, a minority in Manhattan and Brooklyn drive the tail.

→ [NB03 — Spatial Analysis](notebooks/03_spatial_analysis.ipynb) · [Interactive station risk map](outputs/figures/03_station_risk_map.html)

### Temporal Multiplier

Accident risk varies sharply by time. NYPD data shows a clear peak between 3–6 PM and elevated risk on weekdays vs. weekends. Manhattan and Brooklyn account for >60% of all bicycle crashes. The temporal multiplier adjusts each trip's risk by its hour and day-of-week, derived directly from the crash distribution below.

![Bike accidents by borough, hour of day, and injury count](outputs/figures/02_nypd_patterns.png)

→ [NB02 — NYPD Patterns](notebooks/02_eda_nypd.ipynb)

### Rider Multiplier

Casual riders take ~50% longer trips than members (median 12.2 min vs. 8.0 min), meaning more time in traffic and higher exposure per trip. The rider multiplier uses this duration ratio as an exposure proxy — casual riders pay a proportionally higher premium.

![Rider type distribution and trip duration by segment](outputs/figures/01_rider_segments.png)

→ [NB01 — Rider Segments](notebooks/01_eda_citibike.ipynb)

### Premium Calculation

The raw risk score is min-max normalized across all trips and mapped to a premium:

```
premium = $0.50 + normalized_risk × $1.50
```

- **$0.50 floor** — covers expected loss ($0.13/trip) + admin costs, even for lowest-risk rides
- **$2.00 ceiling** — highest-risk trips (Manhattan, Friday 4 PM, casual rider) carry a meaningful premium, still under half the casual ride price
- **$0.68 average** — validated against top-down actuarial estimates

The heatmap below shows how premiums vary across hour and day-of-week:

![Average premium by hour × day of week](outputs/figures/04_premium_heatmap.png)

→ [NB04 — Risk Model & Premium Calculator](notebooks/04_risk_model.ipynb)


## Business Case

| Metric | Value |
|---|---|
| Expected loss per trip | $0.13 |
| Average premium (from risk model) | $0.68 |
| Gross Written Premium (base case) | ~$573K / year |
| Loss ratio | ~19% |
| Combined ratio (incl. admin + rev share) | ~29% |
| AXA net margin | ~61% |

**Top-down validation:** ~6,700 NYC bike crashes → ~1,300–2,000 involving CitiBike-type riders → ~800 claims at 50% claim rate × $1,500 avg payout = ~$1.2M total loss across ~9.3M trips → **$0.13 expected loss per trip**. The formula handles risk differentiation (who pays more vs. less); the aggregate data sets the price level.

→ [NB04 — Business Case Section](notebooks/04_risk_model.ipynb)

## Next Steps & Further Considerations

**Path to ML.** A supervised model is feasible via **spatio-temporal proxy labeling**. The idea: join the ~6,700 geocoded + timestamped NYPD crashes against ~9.3M geocoded + timestamped CitiBike trips. Trips that were active near a crash location (≤250m) within a time window (±30 min) are labeled `accident_proximal = 1`; everything else is `0`.

This label isn't "this rider had an accident" — it's "a real accident happened near where and when this rider was riding." That's noisy, but it's a legitimate exposure proxy. 

A model trained on this target (XGBoost, logistic regression) could capture patterns the formula cannot:
- **Interactions** — a specific station may be dangerous only during rush hour, not uniformly
- **Seasonality** — summer vs. winter crash patterns per station -> increase data to cover years before 2025.
- **Non-linear effects** — risk may not scale linearly with raw accident count
- **Temporal granularity** — date-level variation instead of year-aggregated multipliers

**Caveats for solving this problem using machine learning:**
- **Class imbalance** — <0.1% positive rate (6,700 in 9.3M) requires careful calibration, and the lift over the formula may be marginal
- **Ecological label** — "a crash happened nearby" ≠ "this rider crashed," so the signal-to-noise ratio is low
- **Validation gap** — without real claims, we can't measure whether the ML model actually prices risk better
- **Explainability** — a formula premium decomposes into 3 transparent factors; XGBoost requires SHAP for regulatory compliance (EU AI Act Art. 13)

The formula serves as a production-ready baseline. Once real claims data accumulates (6–12 months post-launch), train a supervised model on actual outcomes and validate whether it outperforms the formula on held-out claims. Every adjuster-corrected auto-assessment also becomes labelled training data for continuous improvement.

**Route-level risk.** Current model scores departure stations. With GPS traces from the CitiBike app, score the actual route — a rider on 8th Avenue (protected bike lane) has meaningfully different risk than one on 6th Avenue (no lane, high taxi density).

**GenAI in Claims.** Four high-leverage applications for the claims lifecycle:

- **FNOL Chatbot** — LLM-guided claim intake in the CitiBike app. Pre-fills trip context (GPS, timestamp), captures injury details in <3 minutes vs. 30-minute call centre average.
- **Photo Damage Assessment** — Rider uploads damage photos, vision model estimates severity and repair cost. ~65% of low-severity claims (dooring, falls) become eligible for straight-through processing.
- **Document Intelligence** — LLM extracts structured fields from medical reports and repair invoices, replacing manual data entry (8–12 min → <5 sec per document).
- **GPS Fraud Detection** — Automatic plausibility check: compare reported accident location against actual trip GPS track. A free fraud signal unique to bike-share — traditional insurers don't have trip-level data.

All GenAI components are designed for augmentation with human-in-the-loop oversight, audit trails, and EU AI Act compliance.
