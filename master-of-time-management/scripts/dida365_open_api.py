import calendar
import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_SHANGHAI = ZoneInfo("Asia/Shanghai")

TASK_API_BASE = "https://api.dida365.com/open/v1"
COMPLETED_TASK_URL = f"{TASK_API_BASE}/task/completed"
PROJECT_URL = f"{TASK_API_BASE}/project"

DEFAULT_SNAPSHOT_DIR = Path.home() / ".dida365"


def is_date_string(value: str | None) -> bool:
    """Return whether value is a valid YYYY-MM-DD date string."""
    if not value:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _parse_local_date(value: str) -> date:
    """Parse a local YYYY-MM-DD date string."""
    return datetime.strptime(value, "%Y-%m-%d").date()


def _format_date_only(d: date) -> str:
    """Format a date as YYYY-MM-DD."""
    return d.strftime("%Y-%m-%d")


def _add_days(d: date, days: int) -> date:
    """Return a date offset by the given number of days."""
    return d + timedelta(days=days)


def build_date_ranges(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """Split an inclusive date range into month-bounded API query ranges."""
    ranges: list[tuple[str, str]] = []
    cursor = _parse_local_date(start_date)
    end = _parse_local_date(end_date)
    if cursor > end:
        raise ValueError("开始日期不能晚于结束日期")
    while cursor <= end:
        range_start = cursor
        last_dom = date(
            cursor.year,
            cursor.month,
            calendar.monthrange(cursor.year, cursor.month)[1],
        )
        actual_end = last_dom if last_dom < end else end
        ranges.append((_format_date_only(range_start), _format_date_only(actual_end)))
        cursor = _add_days(actual_end, 1)
    return ranges


def to_dida_datetime(day: str, is_end_of_day: bool) -> str:
    """Convert a date string to the Dida365 API datetime format."""
    tail = "23:59:59.999" if is_end_of_day else "00:00:00.000"
    return f"{day}T{tail}+0800"


def _request_json(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> Any:
    """Send an authenticated JSON request and decode the JSON response."""
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8") if e.fp else ""
        try:
            err = json.loads(text) if text else {}
        except json.JSONDecodeError:
            err = {"message": text or str(e)}
        msg = err.get("errorMessage") or err.get("message") or f"HTTP {e.code}"
        raise RuntimeError(msg) from e
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}


def fetch_projects(token: str) -> list[dict[str, Any]]:
    """Fetch projects from the Dida365 Open API."""
    data = _request_json("GET", PROJECT_URL, token)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        projects = data.get("projects")
        if isinstance(projects, list):
            return [x for x in projects if isinstance(x, dict)]
    return []


def get_project_id(token: str) -> str:
    """Resolve the first available project id for the authenticated account."""
    projects = fetch_projects(token)
    if projects:
        pid = projects[0].get("id")
        if pid:
            return str(pid)
    raise RuntimeError("未获取到 project_id")


def persist_project_id_env(project_id: str) -> None:
    """Store the resolved project id in the current process environment."""
    os.environ["DIDA365_PROJECT_ID"] = project_id


def fetch_completed_for_range(
    token: str,
    project_id: str,
    start_day: str,
    end_day: str,
) -> list[dict[str, Any]]:
    """Fetch completed tasks for one inclusive API date range."""
    body = {
        "projectId": project_id,
        "startDate": to_dida_datetime(start_day, False),
        "endDate": to_dida_datetime(end_day, True),
    }
    data = _request_json("POST", COMPLETED_TASK_URL, token, body)
    if isinstance(data, list):
        return normalize_completed_tasks_for_snapshot(data)
    if isinstance(data, dict):
        for key in ("tasks", "completedTasks"):
            arr = data.get(key)
            if isinstance(arr, list):
                return normalize_completed_tasks_for_snapshot(arr)
    return []


def get_completed_tasks(
    token: str,
    project_id: str | None,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Fetch completed tasks across a date range and deduplicate by task key."""
    if not is_date_string(start_date) or not is_date_string(end_date):
        raise ValueError("日期范围无效")
    pid = project_id
    if pid is None:
        pid = get_project_id(token)
        persist_project_id_env(pid)
    a = _parse_local_date(start_date)
    b = _parse_local_date(end_date)
    task_map: dict[str, dict[str, Any]] = {}
    for start_day, end_day in build_date_ranges(start_date, end_date):
        fetched = fetch_completed_for_range(token, pid, start_day, end_day)
        bounded: list[dict[str, Any]] = []
        for task in fetched:
            tz = resolve_task_zone(task.get("timeZone"))
            day = start_date_to_date_str(task.get("startDate"), tz)
            if not day:
                continue
            d = _parse_local_date(day)
            if d < a or d > b:
                continue
            bounded.append(task)
        for task in bounded:
            key = task.get("id") or "{}-{}-{}".format(
                task.get("title") or "",
                task.get("completedTime") or "",
                task.get("startDate") or "",
            )
            task_map[str(key)] = task
    return list(task_map.values())


def resolve_credentials(
    token: str | None,
    project_id: str | None,
) -> tuple[str, str | None]:
    """Resolve token and optional project id from arguments or environment."""
    t = (
        token
        or os.environ.get("DIDA365_API_KEY", "").strip()
        or os.environ.get("DIDA365_TOKEN", "").strip()
    )
    if not t:
        raise RuntimeError("请设置环境变量 DIDA365_API_KEY 或使用 --token")
    pid = project_id.strip() if project_id else None
    if pid is None:
        env_pid = os.environ.get("DIDA365_PROJECT_ID", "").strip()
        pid = env_pid or None
    return t, pid


_TZ_COLON = re.compile(r"([+-])(\d{2})(\d{2})$")


def _normalize_iso_tz(s: str) -> str:
    """Normalize compact numeric timezone offsets for fromisoformat parsing."""
    m = _TZ_COLON.search(s)
    if m and len(m.group(0)) == 5:
        return s[: m.start()] + f"{m.group(1)}{m.group(2)}:{m.group(3)}"
    return s


def resolve_task_zone(name: Any, fallback: ZoneInfo | None = None) -> ZoneInfo:
    """Resolve a task timezone name, falling back to Asia/Shanghai."""
    fb = fallback or _SHANGHAI
    if isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except Exception:
            pass
    return fb


def _parse_dida_datetime(
    value: Any,
    calendar_tz: ZoneInfo | None = None,
) -> datetime | None:
    """Parse the datetime variants returned by Dida365 into an aware datetime."""
    tz = calendar_tz or _SHANGHAI
    if not value or not isinstance(value, str):
        return None
    s_raw = value.strip()
    if not s_raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s_raw, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    s = _normalize_iso_tz(s_raw)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            return dt.astimezone(tz)
        return dt.replace(tzinfo=tz)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is not None:
                return dt.astimezone(tz)
            return dt.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def task_investment_minutes(task: dict[str, Any]) -> int:
    """Calculate task duration in whole minutes from startDate and dueDate."""
    if task.get("isAllDay"):
        return 0
    tz = resolve_task_zone(task.get("timeZone"))
    a = _parse_dida_datetime(task.get("startDate"), tz)
    b = _parse_dida_datetime(task.get("dueDate"), tz)
    if a is None or b is None:
        return 0
    sec = (b - a).total_seconds()
    if sec <= 0:
        return 0
    return int(sec // 60)


def completed_time_to_date_str(
    completed_time: Any,
    calendar_tz: ZoneInfo | None = None,
) -> str | None:
    """Return the local completion date string for a completedTime value."""
    if not completed_time or not isinstance(completed_time, str):
        return None
    s = completed_time.strip()
    if not s:
        return None
    tz = calendar_tz or _SHANGHAI
    dt = _parse_dida_datetime(s, tz)
    if dt is not None:
        return dt.date().isoformat()
    if len(s) >= 10 and is_date_string(s[:10]):
        return s[:10]
    return None


def start_date_to_date_str(
    start_date: Any,
    calendar_tz: ZoneInfo | None = None,
) -> str | None:
    """Return the local task date string derived from startDate."""
    if not start_date or not isinstance(start_date, str):
        return None
    s = start_date.strip()
    if not s:
        return None
    tz = calendar_tz or _SHANGHAI
    dt = _parse_dida_datetime(s, tz)
    if dt is not None:
        return dt.date().isoformat()
    if len(s) >= 10 and is_date_string(s[:10]):
        return s[:10]
    return None


_SNAPSHOT_DATETIME_KEYS = frozenset(
    {"startDate", "dueDate", "completedTime", "modifiedTime"}
)


def _format_snapshot_datetime_string(value: str, tz: ZoneInfo) -> str:
    """Format a snapshot datetime value as local second-precision text."""
    s_raw = value.strip()
    if not s_raw:
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s_raw, fmt).replace(tzinfo=tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    s = _normalize_iso_tz(s_raw)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        dt = None
    if dt is not None:
        if dt.tzinfo is not None:
            dt = dt.astimezone(tz)
        else:
            dt = dt.replace(tzinfo=tz)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt).astimezone(tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return value


def _normalize_snapshot_datetimes(
    obj: Any,
    inherited_tz: ZoneInfo | None = None,
) -> Any:
    """Recursively normalize known datetime fields in snapshot data."""
    base = inherited_tz or _SHANGHAI
    if isinstance(obj, dict):
        tz = resolve_task_zone(obj.get("timeZone"), base)
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _SNAPSHOT_DATETIME_KEYS and isinstance(v, str):
                out[k] = _format_snapshot_datetime_string(v, tz)
            elif isinstance(v, dict):
                out[k] = _normalize_snapshot_datetimes(v, tz)
            elif isinstance(v, list):
                out[k] = [_normalize_snapshot_datetimes(x, tz) for x in v]
            else:
                out[k] = v
        return out
    if isinstance(obj, list):
        return [_normalize_snapshot_datetimes(x, inherited_tz) for x in obj]
    return obj


def normalize_completed_tasks_for_snapshot(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize completed tasks before persisting them as local snapshots."""
    return [_normalize_snapshot_datetimes(t) for t in tasks if isinstance(t, dict)]


def bucket_tasks_by_completed_day(
    tasks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group completed tasks by their local startDate day."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        tz = resolve_task_zone(task.get("timeZone"))
        day = start_date_to_date_str(task.get("startDate"), tz)
        if not day:
            continue
        buckets.setdefault(day, []).append(task)
    return buckets


def _task_key(task: dict[str, Any]) -> str:
    """Return the stable key used to deduplicate completed task snapshots."""
    k = task.get("id")
    if k is not None:
        return str(k)
    return "{}-{}-{}".format(
        task.get("title") or "",
        task.get("completedTime") or "",
        task.get("startDate") or "",
    )


def save_completed_snapshot(
    path: Path,
    tasks: list[dict[str, Any]],
    merge: bool = True,
) -> None:
    """Write one day's completed-task snapshot, optionally merging old entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, Any]] = {}
    if merge and path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = []
        if isinstance(raw, list):
            for t in raw:
                if isinstance(t, dict):
                    existing[_task_key(t)] = t
    for t in tasks:
        if isinstance(t, dict):
            existing[_task_key(t)] = t
    out = list(existing.values())
    path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_completed_snapshots_by_day(
    base_dir: Path | str,
    tasks: list[dict[str, Any]],
    merge: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Persist completed tasks into one JSON snapshot file per completed day."""
    base = Path(base_dir)
    norm = normalize_completed_tasks_for_snapshot(tasks)
    if start_date is not None and end_date is not None:
        a = _parse_local_date(start_date)
        b = _parse_local_date(end_date)
        if a > b:
            raise ValueError("开始日期不能晚于结束日期")
        bounded: list[dict[str, Any]] = []
        for task in norm:
            tz = resolve_task_zone(task.get("timeZone"))
            day = start_date_to_date_str(task.get("startDate"), tz)
            if not day:
                continue
            d = _parse_local_date(day)
            if d < a or d > b:
                continue
            bounded.append(task)
        norm = bounded
    buckets = bucket_tasks_by_completed_day(norm)
    written: list[Path] = []
    for day in sorted(buckets.keys()):
        p = base / f"{day}.json"
        save_completed_snapshot(p, buckets[day], merge=merge)
        written.append(p)
    return written, norm


def iter_dates_inclusive(start_date: str, end_date: str) -> list[str]:
    """Return every YYYY-MM-DD date in an inclusive date range."""
    a = _parse_local_date(start_date)
    b = _parse_local_date(end_date)
    if a > b:
        raise ValueError("开始日期不能晚于结束日期")
    out: list[str] = []
    c = a
    while c <= b:
        out.append(_format_date_only(c))
        c = _add_days(c, 1)
    return out


def load_completed_snapshot(path: Path) -> list[dict[str, Any]]:
    """Load one snapshot file, returning only task dictionaries."""
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def load_completed_snapshots_range(
    base_dir: Path | str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Load and deduplicate completed-task snapshots across a date range."""
    base = Path(base_dir)
    task_map: dict[str, dict[str, Any]] = {}
    for day in iter_dates_inclusive(start_date, end_date):
        for task in load_completed_snapshot(base / f"{day}.json"):
            task_map[_task_key(task)] = task
    return list(task_map.values())
