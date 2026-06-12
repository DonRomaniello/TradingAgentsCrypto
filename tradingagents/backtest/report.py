"""Render a BacktestResult to markdown + JSON on disk."""

from __future__ import annotations

import json
from pathlib import Path

from tradingagents.backtest.engine import BacktestResult


def _fmt(value, pct: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2%}" if pct else f"{value:.2f}"


def render_markdown(result: BacktestResult) -> str:
    m = result.metrics
    hit_rate = f"{m['hit_rate']:.0%}" if m["hit_rate"] is not None else "n/a"
    lines = [
        f"# Backtest: {result.ticker} ({result.start_date} → {result.end_date})",
        "",
        "## Summary",
        "",
        "| Metric | Strategy | Buy & Hold |",
        "|---|---|---|",
        f"| Total return | {_fmt(m['total_return'], pct=True)} | {_fmt(m['buy_hold_return'], pct=True)} |",
        f"| Annualised return | {_fmt(m['annualised_return'], pct=True)} | — |",
        f"| Sharpe (0% rf) | {_fmt(m['sharpe'])} | {_fmt(m['buy_hold_sharpe'])} |",
        f"| Max drawdown | {_fmt(m['max_drawdown'], pct=True)} | {_fmt(m['buy_hold_max_drawdown'], pct=True)} |",
        "",
        f"- Excess vs buy & hold: **{_fmt(m['excess_vs_buy_hold'], pct=True)}**",
        f"- Directional hit rate: **{hit_rate}**"
        f" ({m['n_directional']} directional of {m['n_decisions']} decisions)",
        f"- Total trading costs: {_fmt(m['total_costs'], pct=True)} of equity",
        f"- Price bars: {m['bars']}",
        "",
        "## Decisions",
        "",
        "| Date | Rating | Exposure | Fwd return | Correct |",
        "|---|---|---|---|---|",
    ]
    for d in result.decisions:
        fwd = _fmt(d.get("forward_return"), pct=True) if d.get("forward_return") is not None else "—"
        correct = {True: "✓", False: "✗", None: "—"}[d.get("correct")]
        lines.append(
            f"| {d['date']} | {d['rating']} | {d['exposure']:.2f} | {fwd} | {correct} |"
        )

    lines += ["", "## Data integrity caveats", ""]
    lines += [f"- {w}" for w in result.warnings]
    lines.append("")
    return "\n".join(lines)


def save_report(result: BacktestResult, out_dir: str | Path) -> tuple[Path, Path]:
    """Write markdown and JSON reports; returns their paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"backtest_{result.ticker}_{result.start_date}_{result.end_date}"

    md_path = out / f"{stem}.md"
    md_path.write_text(render_markdown(result), encoding="utf-8")

    json_path = out / f"{stem}.json"
    payload = {
        "ticker": result.ticker,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "metrics": result.metrics,
        "decisions": result.decisions,
        "equity": {str(k.date()): float(v) for k, v in result.equity.items()},
        "warnings": result.warnings,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return md_path, json_path
