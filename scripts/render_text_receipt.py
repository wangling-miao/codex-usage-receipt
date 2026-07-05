#!/usr/bin/env python3
"""Render a plain-text Codex usage receipt from codex_usage_summary.py JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def number(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "N/A"


def percent(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def line(char: str = "-", width: int = 96) -> str:
    return char * width


def render(summary: dict[str, Any]) -> str:
    total = summary.get("total") or {}
    components = total.get("cost_components_usd") or {}
    models = summary.get("models") or []
    by_source = summary.get("by_source") or {}
    limits = summary.get("rate_limits") or {}

    rows: list[str] = []
    rows.append("CODEX TOKEN USAGE RECEIPT")
    rows.append(line("="))
    rows.append(f"Period:     {summary.get('since', 'N/A')} -> {summary.get('through', 'N/A')}")
    rows.append(f"Generated:  {summary.get('generated_at', 'N/A')}")
    rows.append(f"Total due:  {money(total.get('cost_usd'))}")
    rows.append("")
    rows.append("SUMMARY")
    rows.append(line())
    rows.append(f"Total token volume: {number(total.get('input_plus_output_tokens'))}")
    rows.append(f"Fresh input:        {number(total.get('fresh_input_tokens'))}")
    rows.append(f"Cache-hit input:    {number(total.get('cached_input_tokens'))}")
    rows.append(f"Output tokens:      {number(total.get('output_tokens'))}")
    rows.append(f"Cache hit ratio:    {percent(total.get('cache_hit_ratio_percent'))}")
    rows.append(f"Usage events:       {number(total.get('events'))}")
    rows.append("")
    rows.append("LINE ITEMS BY MODEL")
    rows.append(line())
    rows.append(
        f"{'Model':<26} {'Events':>8} {'Fresh input':>15} {'Cache hit':>15} "
        f"{'Output':>12} {'Rate I/C/O':>18} {'Cost':>12}"
    )
    rows.append(line())
    for row in models:
        rate = (
            f"{row.get('input_rate_per_million_usd', 0):g}/"
            f"{row.get('cache_hit_rate_per_million_usd', 0):g}/"
            f"{row.get('output_rate_per_million_usd', 0):g}"
        )
        rows.append(
            f"{row.get('model', 'unknown'):<26} {number(row.get('events')):>8} "
            f"{number(row.get('fresh_input_tokens')):>15} {number(row.get('cached_input_tokens')):>15} "
            f"{number(row.get('output_tokens')):>12} {rate:>18} {money(row.get('cost_usd')):>12}"
        )
    rows.append(line())
    rows.append(f"{'TOTAL':<26} {number(total.get('events')):>8} {number(total.get('fresh_input_tokens')):>15} "
                f"{number(total.get('cached_input_tokens')):>15} {number(total.get('output_tokens')):>12} "
                f"{'':>18} {money(total.get('cost_usd')):>12}")
    rows.append("")
    rows.append("COST CALCULATION")
    rows.append(line())
    rows.append(f"Fresh input subtotal:      {money(components.get('fresh_input_usd'))}")
    rows.append(f"Cache-hit input subtotal:  {money(components.get('cache_hit_usd'))}")
    rows.append(f"Output subtotal:           {money(components.get('output_usd'))}")
    rows.append(f"Cache creation subtotal:   {money(components.get('cache_creation_usd'))}")
    rows.append(f"Total estimated cost:      {money(total.get('cost_usd'))}")
    rows.append("")
    rows.append("SOURCE COVERAGE")
    rows.append(line())
    for label, row in by_source.items():
        rows.append(
            f"{label}: input {number(row.get('input_tokens'))}, "
            f"cache hit {number(row.get('cached_input_tokens'))}, "
            f"output {number(row.get('output_tokens'))}"
        )
    rows.append("")
    rows.append("CURRENT CODEX LIMIT SNAPSHOT")
    rows.append(line())
    if limits:
        primary = limits.get("primary") or {}
        secondary = limits.get("secondary") or {}
        rows.append(
            f"Primary:   used {percent(primary.get('used_percent'))}, "
            f"remaining {percent(primary.get('remaining_percent'))}, "
            f"reset {primary.get('resets_at', 'N/A')}"
        )
        rows.append(
            f"Secondary: used {percent(secondary.get('used_percent'))}, "
            f"remaining {percent(secondary.get('remaining_percent'))}, "
            f"reset {secondary.get('resets_at', 'N/A')}"
        )
    else:
        rows.append("No rate-limit snapshot found in scanned logs.")
    rows.append("")
    rows.append("Raw JSONL logs only. Local estimate, not an official OpenAI tax invoice.")
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", help="JSON produced by codex_usage_summary.py")
    parser.add_argument("--output", help="Output .txt path. Defaults to stdout.")
    args = parser.parse_args()

    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    text = render(summary)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
