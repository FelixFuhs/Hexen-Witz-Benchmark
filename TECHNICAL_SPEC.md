# **Technische Spezifikation – „Schwerhörige-Hexe Benchmark“**

*Version 1.0 – 31 Mai 2025*

---

## 1 · Projekt-Übersicht

Ein asynchrones Python-Framework misst, wie gut Large-Language-Models (LLMs) phonetische Wortspiele im Stil der „schwerhörigen Hexe“ verstehen und bewertet.
Pipeline:

1. **Generator** – fragt ein Kandidaten-LLM via OpenRouter.
2. **Extractor** – zieht „Gewünscht/Bekommen“ aus der Antwort.
3. **Judge** – lässt ein starkes LLM die Qualität nach Checkliste bewerten.
4. **Storage** – persistiert Roh- und Metadaten, führt Aggregationen.
5. **Analytics** – liefert Kennzahlen & Visuals.

Alle Module sind *stateless*. Persistenz geschieht ausschließlich im Storage-Layer.

---

## 2 · Repository-/File-Struktur

```
schwerhoerige_hexe_benchmark/
├── README.md
├── pyproject.toml
├── .env.example
├── Dockerfile
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── router_client.py
│   ├── generator.py
│   ├── extractor.py
│   ├── judge.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── files.py
│   │   └── database.py
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── visualize.py
│   │   └── dashboard.py
│   ├── cli.py
│   └── main.py
├── tests/
│   ├── test_extractor.py
│   ├── test_models.py
│   └── test_router_client.py
└── benchmarks/               # Laufzeit-Artefakte (git-ignored)
```

### 2.1 Wichtige Dateien

| Datei                      | Inhalt / Zweck                                        | Wichtige Imports                                         |
| -------------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| **pyproject.toml**         | Dependency-Locking (PEP 621, Poetry)                  | httpx, pydantic, pandas, plotly, rich, structlog, sqlite |
| **config.py**              | Alle tuning-Parameter (Model-Liste …); keine Secrets  | from pydantic import BaseSettings                        |
| **models.py**              | Pydantic-Schemas & TypedDicts für jede Pipeline-Stufe | from pydantic import BaseModel, Field                    |
| **router\_client.py**      | Asynchrone HTTP-Abstraktion, Rate-Limiter, Retry      | import httpx, anyio                                      |
| **generator.py**           | `generate_joke()` & orchestrierende Hilfen            | from router\_client import RouterClient                  |
| **extractor.py**           | Regex/LLM-Parsing & Validierung des Summary-Blocks    | re, rapidfuzz                                            |
| **judge.py**               | `judge_response()` via RouterClient                   |                                                          |
| **storage/files.py**       | JSON/CSV-Writer, S3-Backup-Upload                     | json, csv, boto3                                         |
| **storage/database.py**    | SQLite DDL + CRUD; Read-Only in Prod                  | sqlalchemy                                               |
| **analytics/visualize.py** | Plotly-Figure-Fabriken                                | plotly.express                                           |
| **analytics/dashboard.py** | (Optional) Streamlit-App                              | streamlit, plotly                                        |
| **cli.py**                 | Typer-CLI (run, resume, stats)                        | typer                                                    |
| **main.py**                | High-level Orchestration incl. graceful shutdown      | asyncio                                                  |

---

## 3 · Datenfluss-Spezifikation

### 3.1 Pydantic-Modelle

```python
class Summary(BaseModel):
    gewuenscht: str
    bekommen: str

class GenerationResult(BaseModel):
    model: str
    run: int
    summary: Summary
    full_response: str
    prompt_tokens: int
    completion_tokens: int
    timestamp: datetime

class JudgeScore(BaseModel):
    phonetische_aehnlichkeit: int = Field(ge=0, le=35)
    anzueglichkeit: int        = Field(ge=0, le=25)
    logik: int                 = Field(ge=0, le=20)
    kreativitaet: int          = Field(ge=0, le=20)
    gesamt: int                = Field(ge=0, le=100)
    begruendung: Dict[str, str]

class BenchmarkRecord(BaseModel):
    generation: GenerationResult
    judge: JudgeScore
```

All I/O-Funktionen nehmen oder liefern exakt eines dieser Objekte bzw. Listen davon.

### 3.2 Extractor `extract_summary()`

| **Input**  | `str LLM_response`                                                                 |
| ---------- | ---------------------------------------------------------------------------------- |
| **Output** | `Summary`                                                                          |
| **Errors** | `SummaryParseError` – wirft bei fehlender Heading, Bullet-Format oder leerem Wert. |

### 3.3 Router-Call Wrapper

```python
class RouterClient:
    async def chat(
        self,
        model: str,
        prompt: str,
        temperature: float,
    ) -> OpenRouterResponse
```

`OpenRouterResponse` ist ein TypedDict:

```python
class OpenRouterResponse(TypedDict):
    text: str
    prompt_tokens: int
    completion_tokens: int
    status_code: int
    cost_usd: float
```

Die Low-Level-HTTP-Antwort wird sofort in dieses Dict transformiert.

**Fehlerfälle** → spezifische Subklassen von `RouterClientError`:

| Fehler            | Auslöser    | Recovery-Strategie                          |
| ----------------- | ----------- | ------------------------------------------- |
| `RateLimitError`  | HTTP 429    | Exponential Backoff + Jitter, max 5 Retries |
| `ServerError`     | HTTP 5xx    | Retry (3) mit Linear Backoff                |
| `ParseError`      | JSON decode | 0 Retry → fail-fast                         |
| `ConnectionError` | Netzwerk    | Retry bis max 30 s                          |

Alle Fehler werden an den Aufrufer propagiert, dort in `main.py` abgefangen und in die JSON-Logs geschrieben.

---

## 4 · API-Integration (OpenRouter)

| **Setting**             | **Wert**                                                                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Base-URL**            | `https://openrouter.ai/api/v1`                                                                                                                      |
| **Auth**                | `Authorization: Bearer ${OPENROUTER_API_KEY}` (Env-Var)                                                                                             |
| **Timeouts**            | connect = 5 s, read = 90 s                                                                                                                          |
| **Concurrent Requests** | max = **2** gleichzeitig pro LLM (Semaphore)                                                                                                        |
| **Global RPS-Ceiling**  | **60 req/min** (gleitendes Fenster)                                                                                                                 |
| **Retries**             | s.o.                                                                                                                                                |
| **Cost-Berechnung**     | `(prompt_tokens + completion_tokens) / 1 000 * price_per_k` → wird aus Header `x-openrouter-price` gelesen; Fallback: statische Preisliste im Code. |
| **Budget-Guard**        | `config.MAX_BUDGET_USD` – Sobald kumulative Kosten > Budget, beendet sich das Benchmark-Run sauber.                                                 |

---

## 5 · Storage-Schema

### 5.1 Dateisystem

```
benchmarks/<run_id>/
├── raw/
│   └── <model>_<run>.json   # GenerationResult als JSON
├── judged/
│   └── <model>_<run>.json   # BenchmarkRecord als JSON
├── combined.parquet         # alle BenchmarkRecords
├── cost_report.csv          # laufende Kosten
└── meta.json                # Konfiguration & Checksums
```

*Alle Dateien sind append-only; Hash-Werte (SHA-256) sichern Prüfsumme.*

### 5.2 SQLite (analytics only)

```sql
CREATE TABLE records (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  model TEXT,
  run INTEGER,
  gewuenscht TEXT,
  bekommen TEXT,
  phonetische_aehnlichkeit INTEGER,
  anzueglichkeit INTEGER,
  logik INTEGER,
  kreativitaet INTEGER,
  gesamt INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cost_usd REAL,
  ts TIMESTAMP
);
CREATE INDEX idx_model ON records(model);
```

### 5.3 Backups

1. **Local** – täglicher `.tar.zst` Job via `cron`, Aufbewahrung 30 Tage.
2. **Remote** – Upload in S3-Bucket `hexe-bench-backups/` → Lifecycle-Policy: Glacier 90 Tage, Delete 365 Tage.
3. **Disaster Recovery** – Wiederherstellungstest 1×/Quartal; Skript `scripts/restore_check.sh`.

---

## 6 · Logging & Monitoring

| Layer   | Library               | Format                      | Sink          |
| ------- | --------------------- | --------------------------- | ------------- |
| App     | **structlog**         | JSON                        | stdout        |
| HTTP    | httpx events          | JSON                        | stdout        |
| Metrics | **prometheus-client** | /metrics endpoint (uvicorn) | Prometheus    |
| Dash    | Streamlit logs        | plaintext                   | rotating file |

Alerts (Grafana/Prometheus):

* API Error-Rate > 5 % / 5 min
* P99 Latency > 20 s
* Budget > 90 %

---

## 7 · Implementierungs-Reihenfolge & Meilensteine

| Phase | Modul(e)                        | Ziel                                          | Tests                               |
| ----- | ------------------------------- | --------------------------------------------- | ----------------------------------- |
| **0** | `config.py`, `models.py`        | Datenschema fixieren                          | `test_models`                       |
| **1** | `router_client.py`              | Stabile API-Schicht inkl. Retry, Limits, Cost | `test_router_client` mit httpx-Mock |
| **2** | `extractor.py`                  | Summary-Parsing 100 % robust                  | `test_extractor` (+ Fuzz)           |
| **3** | `generator.py`                  | Erste LLM-Calls + local JSON persistieren     | integrierter Smoke-Test             |
| **4** | `judge.py`                      | Bewertungs-Logik vollendet                    | Cross-validation mit Gold-Fixtures  |
| **5** | `storage/`                      | File/SQLite-Persistenz + Cost-Tracker         | transactional tests                 |
| **6** | `main.py`, `cli.py`             | End-to-End MVP (Headless)                     | scenario test                       |
| **7** | `analytics/visualize.py`        | Plot-Erzeugung (.png/.html)                   | visual regression                   |
| **8** | `analytics/dashboard.py`        | Optionales Streamlit Live-Dashboard           | manual QA                           |
| **9** | Dockerfile, CI (GitHub Actions) | `pytest`, `ruff`, `mypy`, publish artefacts   | pipeline green                      |

### MVP-Definition

Phasen 0 – 6 inkl. Box-Plot-PNG & Cost-Report CSV.

### Full Version

Alles bis Phase 9 + Streamlit Dashboard + S3 Backups + Prometheus.

---

## 8 · Edge-Cases & Fehlerbehandlung

| Case                                              | Behandlung                                                                                            |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **LLM liefert keinen Summary-Block**              | GenerationResult wird trotzdem gespeichert; `summary=None`; Judge-Step übersprungen; Severity=WARNING |
| **Judge-JSON parse-bar aber out-of-range Scores** | Clamped + `record.flags.append("judge_score_out_of_range")`                                           |
| **API down > 5 min**                              | Benchmark wird pausiert (Exponential Backoff bis 30 min), dann abgebrochen mit Exit-Code 137          |
| **Disk voll**                                     | `OSError` → Programm-Abbruch; Hinweis im README zum freien Speicher                                   |
| **Budget überschritten**                          | Graceful abort (`end_state="budget_exceeded"`)                                                        |

---

## 9 · Best-Practices-Checkliste (für Implementierung)

* **Typing:** volle `mypy --strict` Abdeckung.
* **Async:** durchgehend `asyncio`, keine Blocking-Calls.
* **Config:** einzig via `pydantic.BaseSettings` (ENV > .env > Defaults).
* **Secrets:** niemals commiten; `.env.example` nutzen.
* **Logging:** keine personenbez. Daten; Level `INFO`.
* **Tests:** > 90 % Coverage; Property-Based für Parsing.
* **CI:** `ruff`, `pytest -q`, `mypy`, `docker build`.
* **Containers:** rootless, non-privileged; healthcheck `python -m schwerhoerige_hexe_benchmark.cli health`.
* **Docs:** README mit Quickstart, Architecture Diagram (PlantUML), Contribution Guide.

---

## 10 · Abhängigkeiten (≥ Version)

| Paket                      | Grund                   |
| -------------------------- | ----------------------- |
| **python** ≥ 3.11          | `taskgroup` API         |
| **httpx** 1.0              | Async HTTP              |
| **anyio** 4.x              | Concurrency Util        |
| **pydantic** 2.x           | Schemas, Settings       |
| **structlog** 24.x         | JSON-Logs               |
| **pandas** 2.x             | DataFrames              |
| **plotly** 5.x             | Interaktive Plots       |
| **sqlite-python** (stdlib) | leichte DB              |
| **typer** 0.12             | CLI                     |
| **prometheus-client** 0.20 | Metrics                 |
| **rapidfuzz** 3.x          | Fuzzy-Match (Extractor) |
| **boto3** 1.x              | S3-Backups              |
| **pytest/pytest-asyncio**  | Tests                   |
| **ruff, mypy**             | Lint, Type-Check        |

---

### **Nächste Schritte**

1. **Repo klonen**, `.env` anlegen, `poetry install`.
2. Milestone 0–2 umsetzen → `pytest -q`.
3. Bei Fragen **README > Architecture** lesen – sollte alles beantworten.

*Damit ist die Spezifikation vollständig; es sollten keine Rückfragen mehr nötig sein.*
