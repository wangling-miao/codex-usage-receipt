#!/usr/bin/env python3
"""Render a LaTeX Codex usage receipt from codex_usage_summary.py JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def tex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def number(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "N/A"


def money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def rate_money(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if abs(numeric - round(numeric, 2)) < 1e-9:
        return f"{numeric:,.2f}"
    return f"{numeric:,.3f}".rstrip("0").rstrip(".")


def percent(value: Any) -> str:
    try:
        return f"{float(value):.1f}\\%"
    except (TypeError, ValueError):
        return "N/A"


def million(value: Any) -> str:
    try:
        return f"{float(value) / 1_000_000:,.6f}"
    except (TypeError, ValueError):
        return "N/A"


def clean_dt(value: Any) -> str:
    if not value:
        return "N/A"
    text = str(value).replace("T", " ")
    return re.sub(r"([0-9]{2}:[0-9]{2}(?::[0-9]{2})?)([+-][0-9]{2}:[0-9]{2})$", r"\1 \2", text)


def receipt_no(summary: dict[str, Any]) -> str:
    since = str(summary.get("since") or "")
    match = re.search(r"(\d{4})-(\d{2})", since)
    if match:
        return f"CODX-{match.group(1)}{match.group(2)}-RAW"
    return "CODX-RAW"


def rate_cell(row: dict[str, Any]) -> str:
    input_rate = rate_money(row.get("input_rate_per_million_usd"))
    cache_rate = rate_money(row.get("cache_hit_rate_per_million_usd"))
    output_rate = rate_money(row.get("output_rate_per_million_usd"))
    return rf"\rate{{{input_rate}}}{{{cache_rate}}}{{{output_rate}}}"


def model_rows(summary: dict[str, Any]) -> list[str]:
    rows = []
    for row in summary.get("models") or []:
        rows.append(
            " & ".join(
                [
                    tex_escape(row.get("model", "unknown")),
                    number(row.get("events")),
                    number(row.get("fresh_input_tokens")),
                    number(row.get("cached_input_tokens")),
                    number(row.get("output_tokens")),
                    rate_cell(row),
                    rf"\money{{{money(row.get('cost_usd'))}}}",
                ]
            )
            + r" \\"
        )
    return rows


def source_rows(summary: dict[str, Any]) -> list[str]:
    rows = []
    for label, row in (summary.get("by_source") or {}).items():
        input_tokens = int(row.get("input_tokens") or 0)
        output_tokens = int(row.get("output_tokens") or 0)
        rows.append(
            " & ".join(
                [
                    tex_escape(label),
                    number(input_tokens),
                    number(row.get("cached_input_tokens")),
                    number(output_tokens),
                    number(input_tokens + output_tokens),
                ]
            )
            + r" \\"
        )
    return rows


def limit_rows(summary: dict[str, Any]) -> list[str]:
    limits = summary.get("rate_limits") or {}
    if not limits:
        return [r"\multicolumn{5}{@{}l@{}}{No rate-limit snapshot found in scanned logs.} \\"]
    rows = []
    for label, key in [("Primary", "primary"), ("Secondary", "secondary")]:
        row = limits.get(key) or {}
        rows.append(
            " & ".join(
                [
                    label,
                    percent(row.get("used_percent")),
                    percent(row.get("remaining_percent")),
                    f"{number(row.get('window_minutes'))} min",
                    tex_escape(clean_dt(row.get("resets_at"))),
                ]
            )
            + r" \\"
        )
    return rows


def render(summary: dict[str, Any]) -> str:
    total = summary.get("total") or {}
    components = total.get("cost_components_usd") or {}
    limits = summary.get("rate_limits") or {}
    captured_at = clean_dt(limits.get("captured_at")) if limits else "N/A"
    total_input = int(total.get("input_tokens") or 0)
    total_output = int(total.get("output_tokens") or 0)

    models = "\n".join(model_rows(summary))
    sources = "\n".join(source_rows(summary))
    limits_table = "\n".join(limit_rows(summary))

    return rf"""\documentclass[UTF8,10pt,a4paper]{{ctexart}}
\usepackage[a4paper,top=9mm,bottom=9mm,left=11mm,right=11mm]{{geometry}}
\usepackage{{array}}
\usepackage{{booktabs}}
\usepackage{{tabularx}}
\usepackage{{xcolor}}
\usepackage{{hyperref}}

\definecolor{{ink}}{{gray}}{{0.06}}
\definecolor{{mid}}{{gray}}{{0.36}}
\definecolor{{line}}{{gray}}{{0.68}}
\definecolor{{pale}}{{gray}}{{0.97}}

\pagestyle{{empty}}
\hypersetup{{hidelinks}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{1.8pt}}
\renewcommand{{\arraystretch}}{{1.08}}

\newcommand{{\summarybox}}[3]{{%
  \fcolorbox{{line}}{{pale}}{{%
    \begin{{minipage}}[t][17mm][c]{{0.305\linewidth}}
      {{\footnotesize\color{{mid}}#1}}\par
      {{\large\bfseries\color{{ink}}#2}}\par
      {{\scriptsize\color{{mid}}#3}}
    \end{{minipage}}}}}}
\newcommand{{\money}}[1]{{\$\,#1}}
\newcommand{{\rate}}[3]{{\begin{{tabular}}{{@{{}}r@{{}}}}\money{{#1}}\\\money{{#2}}\\\money{{#3}}\end{{tabular}}}}

\begin{{document}}

{{\fontsize{{19}}{{21}}\selectfont\bfseries Codex Token Usage Receipt\par}}
{{\normalsize\bfseries Codex Token 消耗收据\par}}
\vspace{{1mm}}
\rule{{\linewidth}}{{0.9pt}}

\begin{{tabularx}}{{\linewidth}}{{@{{}}>{{\raggedright\arraybackslash}}X>{{\raggedleft\arraybackslash}}p{{60mm}}@{{}}}}
\textbf{{Receipt No.}} {tex_escape(receipt_no(summary))} &
\textbf{{Total Estimated Cost}} \quad {{\fontsize{{20}}{{22}}\selectfont\bfseries \money{{{money(total.get("cost_usd"))}}}}} \\
\textbf{{Billing Period}} {tex_escape(clean_dt(summary.get("since")))} -- {tex_escape(clean_dt(summary.get("through")))} &
\textbf{{Currency}} USD, API-equivalent token pricing \\
\textbf{{Prepared For}} Local Codex usage, Windows + WSL Ubuntu &
\textbf{{Generated At}} {tex_escape(clean_dt(summary.get("generated_at")))} \\
\end{{tabularx}}

\vspace{{1mm}}
\summarybox{{Total token volume}}{{{number(total.get("input_plus_output_tokens"))}}}{{input + output, raw session logs}}
\hfill
\summarybox{{Fresh input}}{{{number(total.get("fresh_input_tokens"))}}}{{charged at model input rate}}
\hfill
\summarybox{{Cache hit input}}{{{number(total.get("cached_input_tokens"))}}}{{charged at cached-input rate}}

\vspace{{1mm}}
\summarybox{{Output tokens}}{{{number(total.get("output_tokens"))}}}{{reasoning output included in output}}
\hfill
\summarybox{{Cache hit ratio}}{{{percent(total.get("cache_hit_ratio_percent"))}}}{{cached input / total input}}
\hfill
\summarybox{{Usage events}}{{{number(total.get("events"))}}}{{token\_count events}}

\vspace{{2mm}}
{{\large\bfseries Line Items by Model\par}}
{{\footnotesize\color{{mid}}Rates are USD per 1M tokens in the order input / cache hit / output. Cache creation price is \money{{0.00}}.\par}}

\vspace{{0.5mm}}
{{\footnotesize
\begin{{tabularx}}{{\linewidth}}{{@{{}}>{{\raggedright\arraybackslash}}p{{31mm}}r r r r >{{\raggedleft\arraybackslash}}p{{20mm}} r@{{}}}}
\toprule
\textbf{{Model}} & \textbf{{Events}} & \textbf{{Fresh input}} & \textbf{{Cache hit}} & \textbf{{Output}} & \textbf{{Rate I/C/O}} & \textbf{{Cost}} \\
\midrule
{models}
\midrule
\textbf{{Total}} & \textbf{{{number(total.get("events"))}}} & \textbf{{{number(total.get("fresh_input_tokens"))}}} & \textbf{{{number(total.get("cached_input_tokens"))}}} & \textbf{{{number(total.get("output_tokens"))}}} & \textbf{{--}} & \textbf{{\money{{{money(total.get("cost_usd"))}}}}} \\
\bottomrule
\end{{tabularx}}
}}

\vspace{{2mm}}
{{\large\bfseries Cost Calculation\par}}
{{\footnotesize
\begin{{tabularx}}{{\linewidth}}{{@{{}}>{{\raggedright\arraybackslash}}X r@{{}}}}
\toprule
\textbf{{Charge component}} & \textbf{{Subtotal}} \\
\midrule
Fresh input: {million(total.get("fresh_input_tokens"))}M tokens at model-specific input rates & \money{{{money(components.get("fresh_input_usd"))}}} \\
Cache hit input: {million(total.get("cached_input_tokens"))}M tokens at model-specific cache-hit rates & \money{{{money(components.get("cache_hit_usd"))}}} \\
Output: {million(total.get("output_tokens"))}M tokens at model-specific output rates & \money{{{money(components.get("output_usd"))}}} \\
Cache creation: {number(total.get("cache_creation_tokens"))} tokens at \money{{0.00}}/M & \money{{{money(components.get("cache_creation_usd"))}}} \\
\midrule
\textbf{{Total estimated token cost}} & \textbf{{\money{{{money(total.get("cost_usd"))}}}}} \\
\bottomrule
\end{{tabularx}}
}}

\vspace{{2mm}}
{{\large\bfseries Source Coverage\par}}
{{\footnotesize
\begin{{tabularx}}{{\linewidth}}{{@{{}}l r r r r@{{}}}}
\toprule
\textbf{{Environment}} & \textbf{{Input}} & \textbf{{Cache hit}} & \textbf{{Output}} & \textbf{{Input + output}} \\
\midrule
{sources}
\midrule
\textbf{{Total}} & \textbf{{{number(total_input)}}} & \textbf{{{number(total.get("cached_input_tokens"))}}} & \textbf{{{number(total_output)}}} & \textbf{{{number(total_input + total_output)}}} \\
\bottomrule
\end{{tabularx}}
}}

\vspace{{2mm}}
{{\large\bfseries Current Codex Limit Snapshot\par}}
{{\footnotesize
\begin{{tabularx}}{{\linewidth}}{{@{{}}l r r r r@{{}}}}
\toprule
\textbf{{Window}} & \textbf{{Used}} & \textbf{{Remaining}} & \textbf{{Window length}} & \textbf{{Reset time}} \\
\midrule
{limits_table}
\bottomrule
\end{{tabularx}}
}}

\vspace{{1mm}}
\rule{{\linewidth}}{{0.45pt}}
{{\scriptsize\color{{mid}}
Raw Codex JSONL logs only. Limit snapshot captured from logs at {tex_escape(captured_at)}. Local estimate, not an official OpenAI tax invoice.
}}

\end{{document}}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", help="JSON produced by codex_usage_summary.py")
    parser.add_argument("--output", required=True, help="Output .tex path")
    args = parser.parse_args()

    summary = json.loads(Path(args.summary_json).read_text(encoding="utf-8"))
    Path(args.output).write_text(render(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
