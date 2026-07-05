#!/usr/bin/env python3
"""Summarize Codex token usage from raw JSONL session logs.

The script intentionally uses event_msg/token_count last_token_usage entries by
default. In Codex JSONL files that is the per-event usage, while cumulative
total_token_usage may reset or repeat across compaction and continuation points.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


DEFAULT_PRICES = {
    # USD per 1M tokens: input, cached input, output, cache creation.
    "gpt-5.5": (5.00, 0.50, 30.00, 0.00),
    "gpt-5.4": (2.50, 0.25, 15.00, 0.00),
    "gpt-5.4-mini": (0.75, 0.075, 4.50, 0.00),
    "gpt-5.3-codex": (1.75, 0.175, 14.00, 0.00),
    "gpt-5.3-codex-spark": (1.75, 0.175, 14.00, 0.00),
}


@dataclass
class SourceRoot:
    path: Path
    label: str
    priority: int


def parse_timezone(value: str) -> timezone:
    if value.upper() == "Z":
        return timezone.utc
    sign = 1
    raw = value
    if value.startswith("-"):
        sign = -1
        raw = value[1:]
    elif value.startswith("+"):
        raw = value[1:]
    hours, _, minutes = raw.partition(":")
    return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes or 0)))


def parse_timestamp(value: str | None, local_tz: timezone) -> datetime | None:
    if not value:
        return None
    try:
        raw = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(local_tz)
    except ValueError:
        return None


def parse_boundary(value: str, local_tz: timezone, *, end_of_day: bool = False) -> datetime:
    raw = value.strip()
    if len(raw) == 10:
        parsed_date = datetime.fromisoformat(raw).replace(tzinfo=local_tz)
        if end_of_day:
            return parsed_date.replace(hour=23, minute=59, second=59)
        return parsed_date
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(local_tz)


def default_roots() -> list[SourceRoot]:
    roots: list[SourceRoot] = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        roots.extend(
            [
                SourceRoot(Path(userprofile) / ".codex" / "sessions", "Windows sessions", 2),
                SourceRoot(Path(userprofile) / ".codex" / "archived_sessions", "Windows archived", 1),
            ]
        )

    # Common Codex-on-WSL locations. Add/override with --root if your distro
    # name or Linux user differs.
    roots.extend(
        [
            SourceRoot(Path(r"\\wsl.localhost\Ubuntu\root\.codex\sessions"), "WSL Ubuntu root sessions", 2),
            SourceRoot(Path(r"\\wsl.localhost\Ubuntu\root\.codex\archived_sessions"), "WSL Ubuntu root archived", 1),
        ]
    )
    return roots


def parse_price(value: str) -> tuple[str, tuple[float, float, float, float]]:
    model, sep, rates = value.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError("price must look like model=input,cache,output[,cache_create]")
    parts = [float(part) for part in rates.split(",")]
    if len(parts) == 3:
        parts.append(0.0)
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("price needs 3 or 4 comma-separated numeric rates")
    return model.strip(), (parts[0], parts[1], parts[2], parts[3])


def add_usage(row: dict[str, int], usage: dict[str, Any]) -> None:
    input_tokens = int(usage.get("input_tokens") or 0)
    cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    reasoning_output_tokens = int(usage.get("reasoning_output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
    cache_creation_tokens = int(usage.get("cache_creation_tokens") or 0)

    row["events"] += 1
    row["input_tokens"] += input_tokens
    row["cached_input_tokens"] += cached_input_tokens
    row["fresh_input_tokens"] += max(0, input_tokens - cached_input_tokens)
    row["output_tokens"] += output_tokens
    row["reasoning_output_tokens"] += reasoning_output_tokens
    row["reported_total_tokens"] += total_tokens
    row["cache_creation_tokens"] += cache_creation_tokens


def fmt_dt(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ", timespec="seconds") if value else None


def reset_time(epoch_seconds: Any, local_tz: timezone) -> str | None:
    try:
        return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).astimezone(local_tz).isoformat(
            sep=" ", timespec="minutes"
        )
    except (TypeError, ValueError, OSError):
        return None


def limit_percent_fields(raw_used_percent: Any) -> dict[str, float | None]:
    """Return display-ready limit percentages.

    Codex's JSON field is named used_percent, but for this receipt workflow the
    user-facing columns should treat that raw value as the remaining side of the
    quota display. Keep raw_used_percent for auditability and expose swapped
    used_percent/remaining_percent for renderers.
    """

    if raw_used_percent is None:
        return {"raw_used_percent": None, "used_percent": None, "remaining_percent": None}
    raw = float(raw_used_percent)
    return {"raw_used_percent": raw, "used_percent": 100 - raw, "remaining_percent": raw}


def scan_files(roots: list[SourceRoot]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for root in roots:
        if not root.path.exists():
            continue
        for path in root.path.rglob("*.jsonl"):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append(
                {
                    "path": path,
                    "label": root.label,
                    "priority": root.priority,
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
            )
    return files


def summarize(args: argparse.Namespace) -> dict[str, Any]:
    local_tz = parse_timezone(args.timezone)
    now = datetime.now(local_tz)
    since = parse_boundary(args.since, local_tz)
    until = parse_boundary(args.until, local_tz, end_of_day=True) if args.until else now

    roots = default_roots()
    for item in args.root or []:
        label, sep, path = item.partition("=")
        if sep:
            roots.append(SourceRoot(Path(path), label, 2))
        else:
            roots.append(SourceRoot(Path(item), item, 2))

    prices = dict(DEFAULT_PRICES)
    for model, rate in args.price or []:
        prices[model] = rate

    parsed: list[dict[str, Any]] = []
    for rec in scan_files(roots):
        path: Path = rec["path"]
        session_id = None
        current_model = None
        events: list[tuple[datetime, str, dict[str, Any]]] = []
        last_rate_limits = None

        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = parse_timestamp(obj.get("timestamp"), local_tz)
                    payload = obj.get("payload") or {}
                    record_type = obj.get("type")

                    if record_type == "session_meta":
                        session_id = payload.get("session_id") or payload.get("id") or session_id
                    elif record_type == "turn_context":
                        current_model = payload.get("model") or current_model
                    elif record_type == "event_msg" and payload.get("type") == "token_count":
                        info = payload.get("info") or {}
                        rate_limits = payload.get("rate_limits") or info.get("rate_limits")
                        if rate_limits and ts:
                            last_rate_limits = {"ts": ts, "rate_limits": rate_limits, "path": str(path)}
                        if ts is None or ts < since or ts > until:
                            continue
                        usage = info.get("last_token_usage") or {}
                        if not isinstance(usage, dict):
                            continue
                        total_tokens = int(
                            usage.get("total_tokens")
                            or (int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0))
                        )
                        if total_tokens <= 0:
                            continue
                        model = info.get("model") or payload.get("model") or current_model or "unknown"
                        events.append((ts, model, usage))
        except OSError:
            continue

        if session_id is None:
            session_id = path.stem.replace("rollout-", "")
        parsed.append({**rec, "session_id": session_id, "events": events, "last_rate_limits": last_rate_limits})

    chosen: dict[str, dict[str, Any]] = {}
    for rec in parsed:
        old = chosen.get(rec["session_id"])
        key = (rec["priority"], rec["size"], rec["mtime"])
        if old is None or key > (old["priority"], old["size"], old["mtime"]):
            chosen[rec["session_id"]] = rec

    by_model: defaultdict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_source: defaultdict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total: defaultdict[str, int] = defaultdict(int)
    first_event = None
    last_event = None
    latest_rate_limits = None
    included_sessions = 0

    for rec in chosen.values():
        if not rec["events"]:
            continue
        included_sessions += 1
        if rec["last_rate_limits"] and (
            latest_rate_limits is None or rec["last_rate_limits"]["ts"] > latest_rate_limits["ts"]
        ):
            latest_rate_limits = rec["last_rate_limits"]
        for ts, model, usage in rec["events"]:
            add_usage(by_model[model], usage)
            add_usage(by_source[rec["label"]], usage)
            add_usage(total, usage)
            first_event = ts if first_event is None or ts < first_event else first_event
            last_event = ts if last_event is None or ts > last_event else last_event

    model_rows = []
    cost_components = defaultdict(float)
    total_cost = 0.0
    for model, row in by_model.items():
        input_rate, cached_rate, output_rate, cache_creation_rate = prices.get(model, (0.0, 0.0, 0.0, 0.0))
        fresh_cost = row["fresh_input_tokens"] / 1_000_000 * input_rate
        cache_cost = row["cached_input_tokens"] / 1_000_000 * cached_rate
        output_cost = row["output_tokens"] / 1_000_000 * output_rate
        cache_creation_cost = row["cache_creation_tokens"] / 1_000_000 * cache_creation_rate
        cost = fresh_cost + cache_cost + output_cost + cache_creation_cost
        total_cost += cost
        cost_components["fresh_input_usd"] += fresh_cost
        cost_components["cache_hit_usd"] += cache_cost
        cost_components["output_usd"] += output_cost
        cost_components["cache_creation_usd"] += cache_creation_cost
        model_rows.append(
            {
                "model": model,
                **dict(row),
                "input_rate_per_million_usd": input_rate,
                "cache_hit_rate_per_million_usd": cached_rate,
                "output_rate_per_million_usd": output_rate,
                "cache_creation_rate_per_million_usd": cache_creation_rate,
                "cost_usd": cost,
            }
        )

    model_rows.sort(key=lambda row: row["cost_usd"], reverse=True)

    cache_ratio = None
    if total["input_tokens"]:
        cache_ratio = total["cached_input_tokens"] / total["input_tokens"] * 100

    rate_summary = None
    if latest_rate_limits:
        limits = latest_rate_limits["rate_limits"]
        primary = limits.get("primary") or {}
        secondary = limits.get("secondary") or {}
        primary_percent = limit_percent_fields(primary.get("used_percent"))
        secondary_percent = limit_percent_fields(secondary.get("used_percent"))
        rate_summary = {
            "captured_at": fmt_dt(latest_rate_limits["ts"]),
            "plan_type": limits.get("plan_type"),
            "primary": {
                **primary_percent,
                "window_minutes": primary.get("window_minutes"),
                "resets_at": reset_time(primary.get("resets_at"), local_tz),
            },
            "secondary": {
                **secondary_percent,
                "window_minutes": secondary.get("window_minutes"),
                "resets_at": reset_time(secondary.get("resets_at"), local_tz),
            },
        }

    return {
        "generated_at": fmt_dt(now),
        "since": fmt_dt(since),
        "through": fmt_dt(until),
        "first_event": fmt_dt(first_event),
        "last_event": fmt_dt(last_event),
        "files_found": len(scan_files(roots)),
        "sessions_after_dedupe": len(chosen),
        "included_sessions": included_sessions,
        "models": model_rows,
        "total": {
            **dict(total),
            "input_plus_output_tokens": total["input_tokens"] + total["output_tokens"],
            "cache_hit_ratio_percent": cache_ratio,
            "cost_usd": total_cost,
            "cost_components_usd": dict(cost_components),
        },
        "by_source": {label: dict(row) for label, row in sorted(by_source.items())},
        "rate_limits": rate_summary,
        "pricing": {
            model: {
                "input_per_million_usd": rate[0],
                "cache_hit_per_million_usd": rate[1],
                "output_per_million_usd": rate[2],
                "cache_creation_per_million_usd": rate[3],
            }
            for model, rate in sorted(prices.items())
        },
        "notes": [
            "Uses raw Codex JSONL event_msg/token_count last_token_usage entries.",
            "Cumulative total_token_usage is not used by default because it can reset or repeat across compaction/continuation points.",
            "This is a local estimate, not an official OpenAI invoice.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="Start date/time, e.g. 2026-05-23 or 2026-05-23T00:00:00")
    parser.add_argument("--until", help="End date/time. A date-only value counts through 23:59:59 local time.")
    parser.add_argument("--timezone", default="+08:00", help="Local timezone offset, default +08:00")
    parser.add_argument("--root", action="append", help="Extra root to scan. Use label=path or just path.")
    parser.add_argument("--price", action="append", type=parse_price, help="Override price: model=input,cache,output[,cache_create]")
    parser.add_argument("--output", help="Write JSON to this path instead of stdout")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    args = parser.parse_args()

    result = summarize(args)
    text = json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
