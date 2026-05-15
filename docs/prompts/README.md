# LLM trade framework prompts

These files extend the analyst LLM (`agents/chatgpt_analyst_agent.py`) **system** context. They are versioned product copy, not secrets.

| File | Purpose |
|------|---------|
| [PROFESSIONAL_BULLISH_ANALYST.md](PROFESSIONAL_BULLISH_ANALYST.md) | Structured bullish setup framework (reason → execution). |
| [VOLUME_IGNITION_SCANNER.md](VOLUME_IGNITION_SCANNER.md) | US volume-ignition scanner criteria and output shape. |

**Env**

- `LLM_TRADE_FRAMEWORK_ENABLED` — default `true`; set `false` to skip loading these files.
- `LLM_APPEND_IGNITION_SCANNER_PROMPT` — default `true` when `STRATEGY_MODE=volume_ignition`; set `false` to skip the ignition scanner appendix.

Mechanical volume-ignition filters remain in [agents/strategy_volume_ignition.py](../../agents/strategy_volume_ignition.py). Paper orders still use strategy stops / TP + RiskManager + LLM `allow_order`; `trade_plan_markdown` is advisory text for Telegram/logs.
