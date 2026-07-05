---
name: codex-usage-receipt
description: Use this skill whenever the user asks for Codex token usage, Codex cost, token consumption since a date, remaining Codex quota/limits, cache-hit tokens, model-by-model pricing, or a receipt/report/PDF/printout for Codex usage. This skill should also trigger for Chinese prompts asking to print a Codex token spending receipt, show token consumption and quota remainder, count both Windows and WSL, list model prices, or make the result look like a receipt/report. It is especially important when raw Windows and WSL Codex JSONL logs must be reconciled and when the output should be a polished black-and-white receipt rather than a prose explanation.
---

# Codex Usage Receipt

This skill turns local Codex JSONL session logs into a model-by-model token usage receipt. It is optimized for the workflow where the user wants something printable: totals, model names, per-model prices, estimated USD cost, cache hit details, and a current Codex limit snapshot.

## First Step: Confirm The Time Period

Before scanning logs, calculating totals, generating a receipt, or printing anything, ask the user what time period they want to count.

- If the user already gave an explicit period in the current request, briefly restate it and proceed. Example: "I will count 2026-05-23 00:00:00 through now."
- If the user only says "recently", "this month", "since last time", or does not mention a period, ask a concise follow-up question and wait for the answer.
- Convert the answer into an absolute local start and end time before running the script. Use the user's local timezone unless they specify another timezone.

## Core Principles

- Treat raw Codex JSONL logs as the primary source. Do not use CC Switch, dashboards, screenshots, or rollups as the source of truth unless the user explicitly asks for reconciliation.
- Include both Windows and WSL logs by default. A Windows-only scan can miss most of the usage.
- Use `event_msg` records with `payload.type == "token_count"` and `info.last_token_usage` as the default usage event. Avoid summing `total_token_usage` directly because it is cumulative and can reset or repeat across compaction and continuation points.
- Track the active model from the latest preceding `turn_context.payload.model`; use any model field on the token event if present.
- Make the output look like a receipt or expense report, not a medical/lab report and not a long explanation.
- If the user asks for printing, render to grayscale and force the printer job to black-and-white when possible.

## Default Price Table

Use USD per 1M tokens in this order: input / cache hit input / output / cache creation.

| Model | Input | Cache hit | Output | Cache creation |
|---|---:|---:|---:|---:|
| `gpt-5.5` | `$5.00` | `$0.50` | `$30.00` | `$0.00` |
| `gpt-5.4` | `$2.50` | `$0.25` | `$15.00` | `$0.00` |
| `gpt-5.4-mini` | `$0.75` | `$0.075` | `$4.50` | `$0.00` |
| `gpt-5.3-codex` | `$1.75` | `$0.175` | `$14.00` | `$0.00` |
| `gpt-5.3-codex-spark` | `$1.75` | `$0.175` | `$14.00` | `$0.00` |

If the user asks for current/latest official rates, verify with official OpenAI pricing pages before finalizing. If a model is not in the table and the user did not provide a rate, show it as "unpriced" or ask for the price if the cost materially matters. Do not silently map an unknown model to a different model.

## Use The Bundled Script

Prefer the bundled script for the usage calculation:

```powershell
python scripts\codex_usage_summary.py `
  --since 2026-05-23 `
  --until 2026-07-05 `
  --timezone +08:00 `
  --output work\codex-usage-summary.json
```

Override or add prices when needed:

```powershell
python scripts\codex_usage_summary.py `
  --since 2026-05-23 `
  --until 2026-07-05 `
  --price gpt-5.3-codex-spark=1.75,0.175,14,0 `
  --output work\codex-usage-summary.json
```

Add non-default log roots with `--root label=path`, for example:

```powershell
python scripts\codex_usage_summary.py `
  --since 2026-05-23 `
  --until 2026-07-05 `
  --root "WSL home=\\wsl.localhost\Ubuntu\home\<linux-user>\.codex\sessions" `
  --output work\codex-usage-summary.json
```

The script outputs:

- `models[]`: per-model events, fresh input, cache-hit input, output, rates, and cost.
- `total`: total token volumes, `input_plus_output_tokens`, cache hit ratio, cost components, and total cost.
- `by_source`: Windows/WSL source coverage.
- `rate_limits`: latest current Codex rate-limit snapshot, if present in logs.
- `notes`: methodology warnings to carry into footnotes if useful.

## Receipt Layout

For a polished PDF, use LaTeX when available. If another document format is requested, keep the same information hierarchy.

If LaTeX is not installed or compilation fails for environment reasons, fall back gracefully instead of blocking the task:

1. Use Python to render a plain-text receipt from the summary JSON:

```powershell
python scripts\render_text_receipt.py `
  work\codex-usage-summary.json `
  --output outputs\codex-usage-receipt.txt
```

2. If a PDF/PNG is still required and Python libraries such as ReportLab, Pillow, or browser-based HTML-to-PDF tooling are already available, use them. Do not install heavy dependencies unless the user approves.
3. If no rendering stack is available, provide the `.txt` receipt and, for print requests, print the text directly.

Recommended one-page A4 structure:

1. Header: `Codex Token Usage Receipt`, receipt number, billing period, generated timestamp, currency, total estimated cost.
2. Summary boxes: total token volume, fresh input, cache-hit input, output, cache-hit ratio, usage event count.
3. Main line-item table by model:
   - model
   - usage events
   - fresh input
   - cache-hit input
   - output
   - rate input/cache/output
   - cost
4. Cost calculation table:
   - fresh input subtotal
   - cache-hit subtotal
   - output subtotal
   - cache creation subtotal, usually `$0.00`
   - total estimated cost
5. Source coverage table: Windows vs WSL totals.
6. Current Codex limit snapshot: primary and secondary used/remaining percentages, window length, reset time.
7. Short footer: raw JSONL logs only; local estimate, not an official tax invoice.

Use black, gray, rules, and tables. Avoid decorative color, hospital-report styling, or paragraph-heavy explanations.

## Calculation Rules

- `fresh_input_tokens = input_tokens - cached_input_tokens`, floored at zero.
- Cost formula:

```text
fresh_input / 1_000_000 * input_rate
+ cached_input / 1_000_000 * cache_hit_rate
+ output / 1_000_000 * output_rate
+ cache_creation / 1_000_000 * cache_creation_rate
```

- Reasoning output is included in output tokens unless the logs or pricing source explicitly says otherwise.
- Cache creation is `$0.00/M` by default for this receipt workflow. If cache-creation tokens appear and the user provides a nonzero rate, include it as a separate line.
- Be explicit about the time window. For relative dates like "since May 23", convert to an absolute local start date such as `2026-05-23 00:00:00 +08:00`.

## Printing Workflow

When the user asks to print:

1. Generate a PDF or high-resolution PNG first.
   - Preferred: LaTeX PDF rendered to grayscale PNG.
   - Fallback: Python-generated text receipt or pure text file.
2. Render the PDF to grayscale:

```powershell
& "C:\Program Files\texlive\2026\bin\windows\pdftoppm.exe" -singlefile -png -gray -r 300 receipt.pdf receipt-print
```

3. Print with a Windows `System.Drawing.Printing.PrintDocument` job and set:

```powershell
$doc.DefaultPageSettings.Color = $false
$e.PageSettings.Color = $false
```

4. Verify the printer queue afterward:

```powershell
Get-PrintJob -PrinterName "<Printer Name>" -ErrorAction SilentlyContinue
Get-Printer -Name "<Printer Name>" | Select Name,PrinterStatus,JobCount,WorkOffline
```

Use the actual printer name on the user's machine. If a printer is offline or invalid, report that clearly instead of claiming it printed.

For a pure-text fallback on Windows:

```powershell
Get-Content outputs\codex-usage-receipt.txt | Out-Printer -Name "<Printer Name>"
```

## Quality Checks

Before finalizing:

- Confirm Windows and WSL source totals are both represented when WSL exists.
- Confirm every model with usage appears in the line-item table.
- Confirm every priced model has rates shown in the report.
- Confirm total cost equals the sum of model rows and cost components.
- Confirm the report does not cite CC Switch as a data source unless the user explicitly asked for CC Switch reconciliation.
- If printed, confirm the queue clears or report the remaining job status.
