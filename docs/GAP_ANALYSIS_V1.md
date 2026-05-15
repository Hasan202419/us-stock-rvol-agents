# Gap Analysis (Spec vs Current Repo)

Repo: `us-stock-rvol-agents`
Reference: `CANONICAL_SPEC_V1.md`

## Ready

- **Scanner pipeline orchestration**: `agents/scan_pipeline.py`
  - strategy mode routing
  - full-scan + ranked signals
  - optional AI-on-fails path
- **Data providers/fallback**: `agents/market_data_agent.py`
  - Alpaca/Polygon/Finnhub/Yahoo/AlphaVantage fallback chain
- **Universe discovery**: `agents/universe_agent.py`
  - Alpaca/Polygon/Finviz path + fallback symbols
- **AI analyst integration**: `agents/chatgpt_analyst_agent.py`
  - DeepSeek/OpenAI with provider selection policy
- **Risk enforcement core**: `agents/risk_manager_agent.py`, `agents/kill_switch.py`
- **Telegram command surface**: `scripts/telegram_command_bot.py`
  - `/scan`, `/signals`, `/help`, backtest utility command path
- **Dashboard runtime**: `dashboard.py`
  - signal table, charts, 3D view, paper readiness context
- **Render deployment skeleton**: `render.yaml`
  - web + worker split
  - environment key mapping
- **Operational scripts**: `scripts/check_apis.py`, `scripts/render_worker_smoke.py`, `scripts/sync_render_telegram_env_and_smoke.ps1`

## Partial

- **Compliance depth (halal gate)**
  - Zoya + configurable thresholds bor, lekin audit-grade policy flags/documented outcomes (unknown/questionable handling)
  bir joyga to'liq standardlashmagan.
- **Execution governance**
  - semi-auto controls mavjud, lekin signal->approval->order->fill audit trail DB model bilan to'liq normalizatsiya qilinmagan.
- **Analytics schema**
  - loglar mavjud, ammo `scan_runs/signals/orders/fills/equity_curve` formal relational contract sifatida to'liq birlashtirilmagan.
- **Provider observability**
  - fallback ishlaydi, ammo Telegram summaryda provider-source breakdown va top-failed-rules default ko'rinishda yo'q (stage-A target).
- **Paper->live gate**
  - prinsip bor, lekin KPI threshold passing check kodda “release gate” ko'rinishida markazlashtirilmagan.

## Missing

- **Single acceptance test suite for governance gates**
  - risk hard-gates + kill-switch + live approval chain uchun yakuniy contract tests.
- **Formal runbook pack**
  - incident matrix (API down, silent bot, empty scan) uchun actionable one-page procedures.
- **Versioned strategy policy registry**
  - parameter versioning + activation metadata (`parameter_versions`) to'liq lifecycle bilan.

## Priority order (implementation)

1. Stage-A diagnostics (`top_failed_rules`, `provider_source_summary`, empty-scan clarity)
2. Risk governance acceptance doc + tests matrix
3. Release checklist/runbook standardization
4. DB lifecycle normalization (scan->signal->order->fill)

