import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dida365_open_api import (
    DEFAULT_SNAPSHOT_DIR,
    get_completed_tasks,
    iter_dates_inclusive,
    load_completed_snapshots_range,
    resolve_credentials,
    resolve_task_zone,
    save_completed_snapshots_by_day,
    start_date_to_date_str,
    task_investment_minutes,
)


def _parse_date(s: str) -> date:
    """Parse a YYYY-MM-DD string into a local date."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def _bucket_day(d: date) -> str:
    """Return the day bucket key used by tag trend output."""
    return d.isoformat()


def _bucket_week(d: date) -> str:
    """Return the ISO week bucket key used by tag trend output."""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _bucket_month(d: date) -> str:
    """Return the calendar month bucket key used by tag trend output."""
    return f"{d.year:04d}-{d.month:02d}"


def _local_snapshots_cover_range(data_dir: Path, start: str, end: str) -> bool:
    """Check whether every day in the requested range has a local snapshot."""
    base = Path(data_dir)
    for day in iter_dates_inclusive(start, end):
        if not (base / f"{day}.json").is_file():
            return False
    return True


def _load_tasks_cache_first(
    start: str,
    end: str,
    data_dir: Path,
    token: str | None,
) -> tuple[list[dict[str, Any]], str]:
    """Load completed tasks from local snapshots, falling back to API refresh."""
    if _local_snapshots_cover_range(data_dir, start, end):
        return load_completed_snapshots_range(data_dir, start, end), "cache"
    cred_token, project_id = resolve_credentials(token, None)
    tasks = get_completed_tasks(cred_token, project_id, start, end)
    save_completed_snapshots_by_day(
        data_dir,
        tasks,
        merge=True,
        start_date=start,
        end_date=end,
    )
    return load_completed_snapshots_range(data_dir, start, end), "api"


def _iter_tags(task: dict[str, Any]) -> list[str]:
    """Return normalized non-empty tag names from a task object."""
    raw = task.get("tags")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def _aggregate_by_tag(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate invested minutes and task counts by tag."""
    by_tag: dict[str, int] = {}
    untagged_minutes = 0
    untagged_count = 0
    total_minutes = 0
    for t in tasks:
        m = task_investment_minutes(t)
        total_minutes += m
        tags = _iter_tags(t)
        if not tags:
            untagged_count += 1
            untagged_minutes += m
            continue
        for name in tags:
            by_tag[name] = by_tag.get(name, 0) + m
    return {
        "byTag": dict(sorted(by_tag.items(), key=lambda x: (-x[1], x[0]))),
        "untaggedMinutes": untagged_minutes,
        "untaggedTaskCount": untagged_count,
        "totalMinutes": total_minutes,
        "totalTasks": len(tasks),
    }


def _filter_tasks_with_tag(tasks: list[dict[str, Any]], tag: str) -> list[dict[str, Any]]:
    """Return tasks that contain the exact requested tag name."""
    want = tag.strip()
    out: list[dict[str, Any]] = []
    for t in tasks:
        if want in _iter_tags(t):
            out.append(t)
    return out


def _trend_for_tag(
    tasks: list[dict[str, Any]],
    tag: str,
    window: str,
    range_start: str,
    range_end: str,
) -> dict[str, Any]:
    """Build a day/week/month minute trend for one tag within a date range."""
    filtered = _filter_tasks_with_tag(tasks, tag)
    a = _parse_date(range_start)
    b = _parse_date(range_end)
    by_bucket: dict[str, int] = {}
    for t in filtered:
        ds = start_date_to_date_str(
            t.get("startDate"),
            resolve_task_zone(t.get("timeZone")),
        )
        if not ds:
            continue
        d = _parse_date(ds)
        if d < a or d > b:
            continue
        if window == "day":
            key = _bucket_day(d)
        elif window == "week":
            key = _bucket_week(d)
        else:
            key = _bucket_month(d)
        m = task_investment_minutes(t)
        by_bucket[key] = by_bucket.get(key, 0) + m
    ordered = dict(sorted(by_bucket.items()))
    return {
        "tag": tag.strip(),
        "window": window,
        "range": {"start": range_start, "end": range_end},
        "minutesByWindow": ordered,
        "totalMatchingMinutes": sum(ordered.values()),
    }


def _cmd_tasks(ns: argparse.Namespace) -> None:
    """Handle the tasks command by fetching completed tasks from the API."""
    token, project_id = resolve_credentials(ns.token, None)
    tasks = get_completed_tasks(token, project_id, ns.start, ns.end)
    out = tasks
    if ns.persist:
        _, out = save_completed_snapshots_by_day(
            ns.data_dir,
            tasks,
            merge=True,
            start_date=ns.start,
            end_date=ns.end,
        )
    if ns.quiet:
        return
    if ns.format == "json":
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for t in out:
            print(json.dumps(t, ensure_ascii=False))


def _cmd_tags(ns: argparse.Namespace) -> None:
    """Handle the tags command by aggregating cached or fetched tasks."""
    tasks, src = _load_tasks_cache_first(ns.start, ns.end, ns.data_dir, ns.token)
    body = _aggregate_by_tag(tasks)
    out = {
        "start": ns.start,
        "end": ns.end,
        "source": src,
        **body,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _cmd_tag_trend(ns: argparse.Namespace) -> None:
    """Handle the tag-trend command by aggregating one tag over time."""
    tasks, src = _load_tasks_cache_first(ns.start, ns.end, ns.data_dir, ns.token)
    out = _trend_for_tag(tasks, ns.tag, ns.window, ns.start, ns.end)
    out["source"] = src
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _add_date_range_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared inclusive date range arguments."""
    parser.add_argument(
        "--start",
        required=True,
        metavar="YYYY-MM-DD",
        help="区间起点（含）；对应当日 00:00:00.000",
    )
    parser.add_argument(
        "--end",
        required=True,
        metavar="YYYY-MM-DD",
        help="区间终点（含）；对应当日 23:59:59.999",
    )


def _add_cache_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared local snapshot cache arguments."""
    parser.add_argument("--token", help="API Key；本地缺日时请求 API（默认环境变量 DIDA365_API_KEY）")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help=f"缓存目录（默认 {DEFAULT_SNAPSHOT_DIR}）",
    )


def _register_tasks_command(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the tasks subcommand."""
    t = sub.add_parser(
        "tasks",
        help="时间范围内任务列表（原始 JSON，走 API）",
        description=(
            "查询指定日期区间内的已完成任务，输出滴答清单 API 返回的原始任务 JSON。"
            "可选择按完成日持久化到本地快照目录。"
        ),
    )
    _add_date_range_args(t)
    t.add_argument("--token", help="API Key；默认环境变量 DIDA365_API_KEY")
    t.add_argument(
        "--format",
        choices=("json", "lines"),
        default="json",
        help="json：数组；lines：每行一条",
    )
    t.add_argument(
        "--persist",
        action="store_true",
        help="按完成日写入 data-dir 下 YYYY-MM-DD.json",
    )
    t.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help=f"持久化目录（默认 {DEFAULT_SNAPSHOT_DIR}）",
    )
    t.add_argument(
        "--quiet",
        action="store_true",
        help="不输出任务 JSON（可配合 --persist）",
    )
    t.set_defaults(_run=_cmd_tasks)


def _register_tags_command(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the tags subcommand."""
    g = sub.add_parser(
        "tags",
        help="按标签聚合；区间内每日本地快照齐全则用缓存，否则拉 API 写入后再算",
        description=(
            "统计指定日期区间内已完成任务的标签投入分钟数、未打标签任务数和总任务数。"
            "优先读取本地每日快照，缺失时自动请求 API 并补齐缓存。"
        ),
    )
    _add_date_range_args(g)
    _add_cache_args(g)
    g.set_defaults(_run=_cmd_tags)


def _register_tag_trend_command(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the tag-trend subcommand."""
    r = sub.add_parser(
        "tag-trend",
        help="单标签趋势；数据加载规则同 tags",
        description=(
            "统计单个标签在指定日期区间内按自然日、ISO 周或自然月聚合的投入分钟趋势。"
            "数据加载规则与 tags 命令一致。"
        ),
    )
    _add_date_range_args(r)
    r.add_argument("--tag", required=True, help="标签名（与任务内 tags 文本一致）")
    r.add_argument(
        "--window",
        required=True,
        choices=("day", "week", "month"),
        help="聚合窗口：day=自然日 week=ISO 周 month=自然月",
    )
    _add_cache_args(r)
    r.set_defaults(_run=_cmd_tag_trend)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for completed-task analysis."""
    p = argparse.ArgumentParser(
        description=(
            "滴答清单已完成任务：查询、按标签汇总、单标签时间窗趋势。"
            "时间范围为日历日；请求 API 时起点日为当日 00:00:00.000、终点日为当日 23:59:59.999（东八区）。"
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    _register_tasks_command(sub)
    _register_tags_command(sub)
    _register_tag_trend_command(sub)
    return p


def main() -> None:
    """Run the CLI entry point."""
    p = build_parser()
    args = p.parse_args()
    try:
        args._run(args)
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
