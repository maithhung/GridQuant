# Masterplan — Short-Term German Electricity Market Intelligence & Simulation Platform

## 0. Executive goal

Build one portfolio project that demonstrates the exact capabilities implied by the target role:

- independent Python development;
- analysis of web data sources and production-grade data collectors;
- parameterization, execution and analysis of market simulations;
- understanding of short-term electricity markets;
- a **fundamental** market model;
- an **AI-based** market-price/market-outcome model;
- reproducible research and experiment management.

### Portfolio project

**Working title:** `DE-SpotLab — Reproducible Short-Term Electricity Market Simulation & Forecasting`

**Research question:**

> How well can a transparent fundamental model and a machine-learning model explain and forecast German day-ahead electricity-market outcomes, and how do changes in renewable generation, demand, fuel costs and cross-border availability alter simulated market outcomes?

The project should end as a small research-grade software package, not merely a notebook.

---

## 1. What the employer is really asking for

| Requirement | Skill demonstrated by the project |
|---|---|
| Eigenständige Entwicklung von Skripten in Python | Python package structure, CLI tools, typing, tests, logging, configuration |
| Analyse von Webdatenquellen | API investigation, schemas, timestamps, units, revisions, missing data |
| Entwicklung von Datenkollektoren | REST/API clients, retries, caching, rate limits, validation, raw/processed layers |
| Parametrierung von Marktsimulationen | scenario files, model parameters, reproducible experiment configuration |
| Durchführung von Marktsimulationen | batch runs, parameter sweeps, simulation engine integration |
| Ergebnisanalyse | statistical analysis, plots, error metrics, market indicators |
| Fundamentale Simulation | merit-order / supply-stack market-clearing model |
| KI-basierte Simulation | time-series ML forecasting + optional agent/bidding extension |
| Forschungsprojekt INTERPRET relevance | modular, explainable, reproducible fundamental + AI workflow |

---

# 2. State-of-the-art skill stack

## Tier 1 — Must-have

### Python engineering

Learn and demonstrate:

- Python 3.11/3.12+
- `uv` or Poetry for dependency management
- `pyproject.toml`
- virtual environments
- functions/classes/modules
- dataclasses and enums
- type hints
- `pathlib`
- exceptions and structured error handling
- logging
- configuration management
- command-line interfaces
- unit/integration tests with `pytest`
- formatting/linting with Ruff
- Git/GitHub workflow

Target standard:

```text
src/
  de_spotlab/
tests/
pyproject.toml
README.md
```

The repository should be installable with one command and runnable without opening a notebook.

---

## Tier 2 — Data engineering

### Data acquisition

You should be able to:

1. find the authoritative source;
2. read its documentation;
3. identify identifiers and geographical zones;
4. determine temporal resolution;
5. determine timezone/DST behavior;
6. identify units;
7. identify publication delays and revisions;
8. build a reliable collector;
9. preserve raw data;
10. transform raw data into analysis-ready tables.

Primary source:

- ENTSO-E Transparency Platform.

ENTSO-E publishes generation, load, transmission and balancing information and provides technical procedures for extracting data. citeturn0search7turn0search9

Useful secondary sources can include:

- German weather data;
- Open-Meteo or another documented weather API;
- publicly available fuel/commodity-price data;
- Bundesnetzagentur / SMARD data;
- European market data where licensing permits.

Do not make the project dependent on scraping a fragile webpage. Prefer documented APIs and downloadable datasets.

### Collector requirements

Implement:

```text
fetch()
validate()
normalize()
cache()
store()
```

The collector must support:

- retries;
- timeouts;
- rate-limit handling;
- caching;
- incremental downloads;
- duplicate detection;
- schema validation;
- missing-value checks;
- timezone normalization;
- raw-data preservation.

---

# 3. Electricity-market knowledge to learn

You do not need to become a trader. You do need to understand the mechanics well enough to explain why the model behaves as it does.

## Core concepts

Learn:

- bidding zones;
- day-ahead market;
- intraday market;
- market coupling;
- merit-order principle;
- supply stack;
- marginal pricing;
- marginal cost;
- start-up costs;
- minimum generation;
- ramp limits;
- block orders;
- demand forecasting;
- renewable forecast uncertainty;
- interconnection;
- congestion;
- negative prices;
- scarcity prices;
- price spikes;
- balancing markets.

Understand the distinction:

```text
physical system
       ↓
fundamentals
       ↓
available supply/demand
       ↓
market orders
       ↓
market clearing
       ↓
zonal price + cleared volume
```

---

# 4. Project architecture

```text
                    ┌──────────────────────┐
                    │ External data sources│
                    │ ENTSO-E / weather /  │
                    │ market fundamentals  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Data collectors      │
                    │ API clients          │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Raw data lake        │
                    │ Parquet / metadata   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │ Validation + feature │
                    │ engineering          │
                    └──────────┬───────────┘
                               │
                 ┌─────────────┴──────────────┐
                 ▼                            ▼
       ┌─────────────────┐          ┌─────────────────┐
       │ Fundamental     │          │ AI model        │
       │ market model    │          │ forecasting     │
       └────────┬────────┘          └────────┬────────┘
                │                            │
                └─────────────┬──────────────┘
                              ▼
                   ┌─────────────────────┐
                   │ Experiment runner   │
                   │ parameter sweeps    │
                   └──────────┬──────────┘
                              ▼
                   ┌─────────────────────┐
                   │ Evaluation + plots  │
                   │ research report     │
                   └─────────────────────┘
```

---

# 5. Data model

Use a canonical timestamp convention internally:

```text
UTC timestamps
+
explicit market timezone metadata
+
market interval identifier
```

Never silently mix local German time and UTC.

Minimum tables:

### `load`

```text
timestamp
zone
forecast_mw
actual_mw
```

### `generation`

```text
timestamp
zone
technology
forecast_mw
actual_mw
```

### `market_price`

```text
timestamp
zone
price_eur_mwh
```

### `weather`

```text
timestamp
latitude
longitude
temperature
wind_speed
solar_radiation
```

### `interconnection`

```text
timestamp
border
available_capacity_mw
scheduled_flow_mw
```

### `fundamentals`

```text
timestamp
gas_price
carbon_price
coal_price
renewable_generation_mw
load_mw
net_import_mw
```

---

# 6. Fundamental model

Start simple. Do not attempt to reproduce EUPHEMIA.

## Version F0 — Merit-order model

Represent generators as:

```text
Generator(
    technology,
    capacity_mw,
    efficiency,
    fuel_cost,
    emission_factor,
    variable_om_cost,
    availability
)
```

Calculate approximate marginal cost:

```text
MC =
    fuel_price / efficiency
    + carbon_price * emission_factor
    + variable_om_cost
```

Create the supply stack:

```text
sort generators by marginal cost
```

Then clear against demand:

```text
dispatch cheapest generation first
until
sum(dispatch) >= demand
```

The marginal dispatched unit determines price.

## Version F1 — Renewable priority

Model wind and solar as low/zero marginal-cost generation with uncertain availability.

## Version F2 — Cross-border imports

Add neighbouring zones or an aggregated import/export term.

## Version F3 — Constraints

Add selected constraints:

- generator availability;
- maximum capacity;
- minimum generation;
- ramp limits;
- interconnector limits.

Do not over-engineer the optimization model before the simple model works.

---

# 7. AI model

The first AI task should be **day-ahead price forecasting**, because it gives a clear supervised-learning problem and a clean benchmark.

## Target

For each market interval:

```text
y_t = day-ahead electricity price
```

## Features

### Calendar

- hour;
- weekday;
- month;
- holiday;
- daylight-related features.

### Market fundamentals

- load;
- wind;
- solar;
- residual load;
- generation mix;
- imports/exports.

### Weather

- temperature;
- wind speed;
- solar radiation.

### Lagged market variables

- price t-1;
- price t-24h;
- price t-48h;
- price t-7d;
- rolling statistics.

Important:

**No future information may leak into the feature set.**

---

# 8. ML progression

Do not jump directly to deep learning.

## Model A — Naive benchmark

```text
price(t) = price(t-24h)
```

## Model B — Linear / regularized regression

Use:

- linear regression;
- Ridge;
- Lasso/Elastic Net.

## Model C — Gradient boosting

Use:

- LightGBM or XGBoost.

This is likely to be the strongest practical baseline.

## Model D — Temporal neural network

Optional:

- Temporal Convolutional Network;
- Long Short-Term Memory network;
- Transformer-style time-series model.

Only add this after the simpler models are properly evaluated.

Recent research continues to combine fundamental market information, machine learning and neural models for day-ahead market forecasting, while newer multi-agent approaches combine spot-market simulation with reinforcement learning. citeturn0search2turn0search8

---

# 9. From AI forecasting to AI market simulation

This is the portfolio differentiator.

Build an optional market-agent layer:

```text
GeneratorAgent
    ↓
forecast market conditions
    ↓
choose bid price / quantity
    ↓
MarketClearing
    ↓
market price
    ↓
profit / reward
```

Start with rule-based bidding.

Then add learning:

```text
state:
    load
    renewable forecast
    fuel costs
    previous prices
    generator availability

action:
    bid-price multiplier
    bid quantity

reward:
    profit
    - penalty for infeasible behaviour
```

You can use reinforcement learning only after the deterministic simulator is stable.

A strong reference point is ASSUME, an open-source Python-based European electricity-market simulation toolbox focused particularly on Germany and integrating deep reinforcement learning for market agents. citeturn0search0turn0search12

---

# 10. Market simulation engine

Implement:

```python
scenario = Scenario.from_yaml("scenarios/germany_2025.yaml")

result = simulate(
    scenario=scenario,
    market="day_ahead",
)
```

The simulation should return structured results:

```text
SimulationResult
├── clearing_price
├── cleared_volume
├── generator_dispatch
├── generator_revenue
├── generator_cost
├── generator_profit
└── diagnostics
```

---

# 11. Scenario system

Use YAML.

Example:

```yaml
scenario:
  name: high_wind_low_demand
  zone: DE_LU

market:
  resolution_minutes: 60
  pricing: marginal

system:
  demand_multiplier: 0.90
  wind_multiplier: 1.30
  solar_multiplier: 1.10

commodities:
  gas_eur_mwh: 35
  carbon_eur_t: 75

interconnection:
  import_capacity_mw: 8000
```

This directly demonstrates **Parametrierung von Marktsimulationen**.

---

# 12. Experiment runner

Implement:

```bash
de-spotlab simulate \
    --scenario scenarios/high_wind.yaml \
    --start 2025-01-01 \
    --end 2025-12-31

de-spotlab forecast \
    --model lightgbm \
    --horizon day-ahead

de-spotlab evaluate \
    --experiment exp_001
```

Store every experiment:

```text
experiments/
  2026-09-12_high_wind/
      config.yaml
      metrics.json
      predictions.parquet
      simulation_results.parquet
      plots/
      log.txt
```

A researcher should be able to reproduce a result months later.

---

# 13. Evaluation

## Forecasting metrics

Use:

- Mean Absolute Error (MAE);
- Root Mean Squared Error (RMSE);
- Mean Absolute Percentage Error only with care around zero prices;
- symmetric MAPE if appropriate;
- correlation;
- directional accuracy;
- spike detection performance.

Also report:

```text
normal hours
negative-price hours
high-price hours
volatile days
```

A single average metric is insufficient for electricity prices.

## Market-simulation metrics

Measure:

- price;
- cleared volume;
- renewable curtailment;
- generator utilization;
- producer surplus;
- consumer surplus if modeled;
- total welfare;
- imports/exports;
- frequency of negative prices;
- frequency of price spikes.

---

# 14. Validation strategy

Use **time-based splits**, never random train/test splitting for the main forecasting experiment.

Example:

```text
2023 ─────────── training
2024 ─────────── validation
2025 ─────────── test
```

Then perform rolling-origin evaluation:

```text
train → forecast → expand training window → forecast → ...
```

This is much closer to real operational forecasting.

---

# 15. Research experiments

The final project should answer at least five questions.

## Experiment 1 — Can fundamentals reproduce price behaviour?

Compare:

```text
actual price
vs
fundamental simulated price
```

Analyze:

- average error;
- systematic bias;
- price spikes;
- renewable-heavy periods.

## Experiment 2 — Does ML outperform the fundamental model?

Compare:

```text
fundamental model
naive forecast
linear model
gradient boosting
```

## Experiment 3 — What drives price?

Use feature importance / explainability.

Analyze:

- residual load;
- wind;
- solar;
- demand;
- fuel costs;
- carbon price;
- imports.

## Experiment 4 — What happens under high renewable penetration?

Scenario:

```text
wind +30%
solar +30%
demand -10%
```

Measure price distribution changes.

## Experiment 5 — What happens under scarcity?

Scenario:

```text
demand +10%
available generation -10%
interconnector capacity -30%
```

Measure:

- price spikes;
- scarcity frequency;
- welfare;
- generator profits.

---

# 16. Optional advanced experiment

If time permits, connect the project to an existing agent-based framework such as ASSUME instead of building a complete reinforcement-learning simulator from scratch.

ASSUME is particularly relevant because it is explicitly designed for European electricity-market simulation, has a German focus, and integrates reinforcement-learning-based agent behaviour. citeturn0search0turn0search20

Your contribution can then be:

```text
public data
      ↓
your collector
      ↓
your preprocessing
      ↓
your scenario generator
      ↓
ASSUME / your market model
      ↓
your AI model
      ↓
your evaluation framework
```

This demonstrates that you can work **with** research software rather than only writing isolated scripts.

---

# 17. Recommended repository

```text
de-spotlab/
│
├── README.md
├── pyproject.toml
├── uv.lock
├── LICENSE
├── masterplan.md
│
├── src/
│   └── de_spotlab/
│       ├── __init__.py
│       ├── cli.py
│       │
│       ├── collectors/
│       │   ├── entsoe.py
│       │   ├── weather.py
│       │   └── base.py
│       │
│       ├── data/
│       │   ├── schemas.py
│       │   ├── validation.py
│       │   └── transformations.py
│       │
│       ├── market/
│       │   ├── generator.py
│       │   ├── merit_order.py
│       │   ├── clearing.py
│       │   └── scenario.py
│       │
│       ├── models/
│       │   ├── baseline.py
│       │   ├── regression.py
│       │   ├── boosting.py
│       │   └── neural.py
│       │
│       ├── experiments/
│       │   ├── runner.py
│       │   └── tracking.py
│       │
│       └── evaluation/
│           ├── metrics.py
│           ├── diagnostics.py
│           └── plots.py
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── configs/
│   ├── data.yaml
│   ├── models.yaml
│   └── experiments.yaml
│
├── scenarios/
│   ├── baseline.yaml
│   ├── high_wind.yaml
│   ├── scarcity.yaml
│   └── interconnector_outage.yaml
│
├── notebooks/
│   └── 01_exploration.ipynb
│
├── reports/
│   └── final_report.md
│
└── data/
    ├── raw/
    ├── processed/
    └── external/
```

---

# 18. 12-week learning + implementation plan

## Week 1 — Python research engineering

### Learn

- modern Python project structure;
- type hints;
- Git;
- testing;
- logging;
- packaging.

### Build

Create the repository and a CLI:

```bash
de-spotlab --help
```

### Acceptance criteria

- installable package;
- Ruff passes;
- tests pass;
- CLI works;
- README explains architecture.

---

## Week 2 — Electricity-market fundamentals

### Learn

- German/EU market structure;
- day-ahead market;
- merit order;
- marginal pricing;
- market coupling;
- negative prices.

### Build

A pure-Python merit-order calculator.

### Acceptance criteria

Given a generator table and demand, the program produces:

```text
dispatch
clearing price
cleared volume
generator profits
```

---

## Week 3 — Web-data engineering

### Learn

- REST APIs;
- HTTP;
- JSON/XML;
- authentication;
- rate limits;
- pagination;
- retries;
- caching.

### Build

ENTSO-E collector.

### Acceptance criteria

```bash
de-spotlab collect entsoe --start ... --end ...
```

works repeatedly without corrupting data.

---

## Week 4 — Data quality

### Learn

- time-series alignment;
- daylight saving time;
- missing data;
- duplicate observations;
- schema validation;
- Parquet.

### Build

Validation pipeline.

### Acceptance criteria

Bad data generates explicit diagnostics rather than silently entering the model.

---

## Week 5 — Exploratory market analysis

### Build

Produce a market dashboard/notebook covering:

- price distribution;
- negative prices;
- daily/weekly seasonality;
- renewable generation;
- residual load;
- price vs residual load.

### Deliverable

`reports/market_analysis.md`

---

## Week 6 — Fundamental simulation

### Build

Implement F0 → F2:

```text
merit order
+
renewables
+
imports
```

### Acceptance criteria

Run one year through the simulator.

Produce:

```text
actual vs simulated price
```

and a quantitative error report.

---

## Week 7 — Simulation parameterization

### Build

YAML scenario system.

Implement:

- high renewable scenario;
- high demand scenario;
- scarcity scenario;
- low interconnection scenario.

### Acceptance criteria

A user can change model assumptions without editing Python source code.

---

## Week 8 — Forecasting baselines

### Build

Models:

1. previous-day naive;
2. linear regression;
3. Ridge/Elastic Net.

### Acceptance criteria

Use a genuine temporal test set and produce a comparison table.

---

## Week 9 — Gradient boosting

### Build

LightGBM/XGBoost model.

Add:

- feature engineering;
- hyperparameter search;
- feature importance;
- SHAP or another explainability method.

### Acceptance criteria

Demonstrate whether the model improves on the baseline.

---

## Week 10 — AI + simulation integration

### Build

Connect AI predictions to the simulation.

Two possible paths:

### Path A — Recommended

Use AI forecasts to parameterize demand/renewable expectations.

### Path B — Advanced

Create learning agents that modify bids.

### Acceptance criteria

The AI component changes simulated market outcomes in a traceable way.

---

## Week 11 — Experimental campaign

Run all scenarios automatically.

Generate:

```text
metrics.csv
plots/
experiment_summary.md
```

Perform sensitivity analysis.

### Acceptance criteria

Every experiment is reproducible from a configuration file.

---

## Week 12 — Portfolio packaging

Create:

### 1. README

Must answer:

- What problem?
- Why electricity markets?
- What data?
- What model?
- What AI?
- What results?
- What limitations?

### 2. Technical report

8–15 pages.

### 3. Architecture diagram

One clean figure.

### 4. Results dashboard

Show:

```text
Actual price
Fundamental simulation
AI forecast
Scenario simulation
```

### 5. Five-minute demo

The ideal demo:

```text
1. run collector
2. inspect data
3. select scenario
4. run simulation
5. run AI forecast
6. compare results
7. explain one interesting market event
```

---

# 19. State-of-the-art extensions

These are **not required for the first portfolio version**.

## A. Probabilistic forecasting

Instead of:

```text
price = 85 €/MWh
```

predict:

```text
P(price)
```

Use:

- quantile regression;
- conformal prediction;
- probabilistic gradient boosting.

## B. Extreme-event modeling

Explicitly model:

- negative prices;
- scarcity events;
- price spikes.

## C. Multi-agent reinforcement learning

Use generator agents with adaptive bidding strategies.

## D. Market-coupling model

Add multiple bidding zones and constrained transmission.

## E. OpenEUPHEMIA research

OpenEUPHEMIA is an open-source effort to reproduce the European day-ahead market-clearing algorithm and is useful for understanding the complexity beyond a simple merit-order model. citeturn0search18

Do not make reproducing EUPHEMIA a prerequisite for the portfolio project.

---

# 20. Technical competencies checklist

Before applying, you should be able to say "yes" to these.

## Python

- [ ] I can create a Python package from scratch.
- [ ] I use type hints.
- [ ] I write tests.
- [ ] I use Git.
- [ ] I can debug an unfamiliar Python codebase.
- [ ] I can build a CLI.
- [ ] I use structured logging.
- [ ] I can profile slow code.

## Data

- [ ] I can investigate an unfamiliar API.
- [ ] I understand API schemas.
- [ ] I handle authentication.
- [ ] I implement retries.
- [ ] I handle rate limits.
- [ ] I validate data.
- [ ] I understand timestamps and DST.
- [ ] I use Parquet.
- [ ] I can work with pandas/Polars.
- [ ] I can design a reproducible ETL pipeline.

## Electricity markets

- [ ] I understand day-ahead market clearing.
- [ ] I understand marginal pricing.
- [ ] I can explain the merit order.
- [ ] I understand residual load.
- [ ] I understand negative prices.
- [ ] I understand cross-border trading at a high level.
- [ ] I can explain the effect of renewable penetration.

## Simulation

- [ ] I can define model parameters.
- [ ] I can run batch simulations.
- [ ] I can perform sensitivity analysis.
- [ ] I can analyze simulation output.
- [ ] I can identify unrealistic model assumptions.

## AI/ML

- [ ] I can construct leakage-free time-series features.
- [ ] I understand temporal validation.
- [ ] I can establish a naive baseline.
- [ ] I can train gradient boosting.
- [ ] I can interpret feature importance.
- [ ] I understand when neural networks are justified.
- [ ] I understand the difference between forecasting and simulation.
- [ ] I can explain model limitations.

## Research

- [ ] Every experiment has a configuration.
- [ ] Results are reproducible.
- [ ] Data provenance is documented.
- [ ] Assumptions are explicit.
- [ ] Results include uncertainty/limitations.
- [ ] I can explain why a result is physically/economically plausible.

---

# 21. What NOT to do

Avoid building a project that is merely:

```text
Jupyter notebook
→ download CSV
→ train XGBoost
→ plot RMSE
```

That demonstrates data science but does not demonstrate the complete job.

Also avoid:

- scraping websites when an official API exists;
- hiding all logic inside notebooks;
- random train/test splitting;
- unexplained hyperparameter tuning;
- claiming causal relationships from correlations;
- building a huge reinforcement-learning system before validating the market model;
- attempting to clone the entire European market;
- optimizing for model complexity instead of research credibility.

---

# 22. Portfolio quality bar

The finished repository should make an employer think:

> "This person could take an unfamiliar electricity-market data source, turn it into a reliable dataset, implement or parameterize a market model, run experiments, analyze the results, and extend the system with AI."

That is more valuable than simply demonstrating that you know Python or machine learning.

---

# 23. Final portfolio deliverables

At completion, the repository should contain:

```text
✓ production-style Python package
✓ documented data collectors
✓ validated electricity-market dataset
✓ fundamental market simulator
✓ configurable scenario system
✓ baseline forecasting models
✓ gradient-boosting AI model
✓ optional AI/agent simulation
✓ automated experiment runner
✓ statistical evaluation
✓ sensitivity analysis
✓ reproducible configurations
✓ tests
✓ technical report
✓ architecture diagram
✓ final results dashboard
✓ five-minute demonstration workflow
```

---

# 24. Employer-facing project description

Use approximately this wording in your CV:

> **DE-SpotLab — Reproducible Short-Term Electricity Market Simulation & Forecasting**
>
> Developed a Python-based research platform for collecting and validating public European electricity-market data, simulating German day-ahead market outcomes using a fundamental merit-order model, and evaluating machine-learning approaches for short-term electricity-price forecasting. Implemented configurable market scenarios, reproducible batch experiments, temporal model validation, automated data-quality checks and quantitative analysis of renewable, demand and interconnection effects.

### Skills to list

```text
Python
Pandas / Polars
REST APIs
Data Engineering
Time-Series Analysis
Electricity Market Modelling
Market Simulation
Machine Learning
Gradient Boosting
Experiment Design
Statistical Evaluation
Git
Pytest
Parquet
Docker
```

Only list tools you actually used.

---

# 25. Interview/demo questions this project prepares you for

Be prepared to answer:

### Data

**"How did you make sure your API data was correct?"**

Discuss:

- source authority;
- schema;
- units;
- timestamps;
- missing data;
- duplicate detection;
- validation;
- raw-data preservation.

### Market model

**"Why does the marginal unit determine price?"**

Explain merit-order clearing and marginal pricing.

### Simulation

**"What assumptions did you make?"**

Be explicit.

### AI

**"How did you prevent leakage?"**

Explain the temporal information boundary.

### Research

**"Why did you choose this model?"**

Answer based on:

```text
baseline
→ incremental complexity
→ empirical improvement
→ interpretability
```

### Model limitations

**"Why doesn't your simulated price exactly match the real market?"**

Mention:

- strategic bidding;
- block orders;
- network constraints;
- market coupling;
- unit commitment;
- forecast errors;
- unavailable/private information;
- non-linear market behaviour.

This answer is more important than pretending the model is perfect.

---

# 26. Definition of done

The project is finished only when a clean machine can execute:

```bash
git clone <repository>
cd de-spotlab

uv sync

uv run pytest

uv run de-spotlab collect \
    --config configs/data.yaml

uv run de-spotlab simulate \
    --scenario scenarios/baseline.yaml

uv run de-spotlab forecast \
    --model gradient_boosting

uv run de-spotlab evaluate \
    --experiment latest
```

and generate the core results without manual notebook manipulation.

---

# 27. Recommended learning priority

If time is limited, prioritize exactly in this order:

```text
1. Python engineering
2. APIs + data collection
3. Electricity-market fundamentals
4. Time-series data engineering
5. Fundamental market simulation
6. Experiment parameterization
7. Time-series ML
8. Evaluation + research methodology
9. Reinforcement learning / multi-agent simulation
10. Advanced market clearing
```

The first eight are enough for a strong application.

The final two are differentiators, not prerequisites.

---

# 28. North-star principle

The project should behave like a **small research laboratory**:

```text
observe the market
      ↓
collect data
      ↓
validate data
      ↓
form a hypothesis
      ↓
parameterize a model
      ↓
run an experiment
      ↓
evaluate the result
      ↓
challenge the assumptions
      ↓
document the conclusion
```

That workflow maps directly onto the job description and is the central skill the portfolio should demonstrate.
