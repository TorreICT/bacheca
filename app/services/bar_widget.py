import json
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings


DEFAULT_COLOR = "#1565C0"
COLOR_PRESETS = {
    "blue": "#1565C0",
    "green": "#2E7D32",
    "red": "#C62828",
    "orange": "#EF6C00",
    "purple": "#6A1B9A",
    "teal": "#00796B",
    "gray": "#455A64",
    "grey": "#455A64",
    "dark": "#202226",
}
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
ANNOUNCEMENT_POLICY = "all active rotate, newest first"

_state_lock = threading.Lock()


def timezone():
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        return ZoneInfo("Europe/Rome")


def now():
    return datetime.now(timezone()).replace(microsecond=0)


def isoformat(value):
    if not value:
        return None
    return value.astimezone(timezone()).replace(microsecond=0).isoformat()


def parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone())
    return parsed.astimezone(timezone()).replace(microsecond=0)


def parse_time(value):
    text = str(value or "").strip()
    if not TIME_RE.match(text):
        raise ValueError("Expected HH:MM or HH:MM:SS")
    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        parts.append(0)
    if parts[0] > 23 or parts[1] > 59 or parts[2] > 59:
        raise ValueError("Invalid time")
    return time(parts[0], parts[1], parts[2])


def format_time(value):
    parsed = parse_time(value)
    return "%02d:%02d:%02d" % (parsed.hour, parsed.minute, parsed.second)


def normalize_color(value):
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in COLOR_PRESETS:
        return COLOR_PRESETS[lowered]
    if HEX_COLOR_RE.match(text):
        return text.upper()
    raise ValueError("Color must be #RRGGBB or one of: " + ", ".join(sorted(COLOR_PRESETS)))


def default_state():
    stamp = isoformat(now())
    return {
        "visible": False,
        "color": DEFAULT_COLOR,
        "announcements": [],
        "countdown": None,
        "soccer": {
            "enabled": False,
            "competition": "SA",
        },
        "updatedAt": stamp,
    }


def load_state():
    path = settings.bar_widget_state_path
    if not path.exists():
        return default_state()
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except Exception:
        return default_state()
    return normalize_state(state)


def save_state(state):
    normalized = normalize_state(state)
    normalized["updatedAt"] = isoformat(now())
    path = settings.bar_widget_state_path
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return normalized


def update_state(mutator):
    with _state_lock:
        state = load_state()
        result = mutator(state)
        if result is not None:
            state = result
        return save_state(state)


def normalize_state(raw):
    state = default_state()
    if not isinstance(raw, dict):
        return state

    state["visible"] = bool(raw.get("visible"))

    try:
        state["color"] = normalize_color(raw.get("color") or DEFAULT_COLOR)
    except ValueError:
        state["color"] = DEFAULT_COLOR

    state["announcements"] = []
    for item in raw.get("announcements") or []:
        try:
            state["announcements"].append(normalize_announcement(item))
        except Exception:
            continue

    try:
        state["countdown"] = normalize_countdown(raw.get("countdown"))
    except Exception:
        state["countdown"] = None

    try:
        state["soccer"] = normalize_soccer(raw.get("soccer"))
    except Exception:
        state["soccer"] = normalize_soccer(None)

    updated_at = raw.get("updatedAt")
    try:
        state["updatedAt"] = isoformat(parse_datetime(updated_at)) if updated_at else state["updatedAt"]
    except Exception:
        pass

    return state


def normalize_announcement(item):
    if not isinstance(item, dict):
        raise ValueError("Announcement must be an object")
    kind = str(item.get("kind") or item.get("type") or "one-shot").strip().lower()
    text = str(item.get("text") or "").strip()
    if not text:
        raise ValueError("Announcement text is required")
    created_at = item.get("createdAt")
    normalized = {
        "id": str(item.get("id") or uuid.uuid4().hex),
        "kind": "periodic" if kind == "periodic" else "one-shot",
        "text": text,
        "createdAt": isoformat(parse_datetime(created_at)) if created_at else isoformat(now()),
    }
    if normalized["kind"] == "periodic":
        normalized.update(normalize_periodic_fields(item))
    else:
        starts_at = parse_datetime(item.get("startsAt"))
        ends_at = parse_datetime(item.get("endsAt"))
        if ends_at <= starts_at:
            raise ValueError("Announcement endsAt must be after startsAt")
        normalized["startsAt"] = isoformat(starts_at)
        normalized["endsAt"] = isoformat(ends_at)
    return normalized


def normalize_periodic_fields(item):
    frequency = str(item.get("frequency") or "").strip().lower()
    if frequency not in ("daily", "weekly"):
        raise ValueError("Periodic frequency must be daily or weekly")

    days = normalize_days_of_week(item.get("daysOfWeek"))
    start_time = format_time(item.get("startTime"))
    end_time_value = item.get("endTime")
    duration_value = item.get("durationMinutes")
    recurrence_ends_at = parse_datetime(item.get("recurrenceEndsAt"))
    starts_at = item.get("startsAt") or item.get("recurrenceStartsAt") or item.get("createdAt")

    if end_time_value:
        end_time = format_time(end_time_value)
        duration_minutes = None
    elif duration_value is not None:
        try:
            duration_minutes = int(duration_value)
        except (TypeError, ValueError):
            raise ValueError("durationMinutes must be a number")
        if duration_minutes <= 0:
            raise ValueError("durationMinutes must be positive")
        end_time = None
    else:
        raise ValueError("Periodic announcements need endTime or durationMinutes")

    fields = {
        "frequency": frequency,
        "daysOfWeek": days,
        "startTime": start_time,
        "recurrenceStartsAt": isoformat(parse_datetime(starts_at)) if starts_at else isoformat(now()),
        "recurrenceEndsAt": isoformat(recurrence_ends_at),
    }
    if end_time:
        fields["endTime"] = end_time
    else:
        fields["durationMinutes"] = duration_minutes
    return fields


def normalize_days_of_week(value):
    if not isinstance(value, list) or not value:
        raise ValueError("daysOfWeek is required")
    days = []
    for item in value:
        parsed = int(item)
        if parsed < 0 or parsed > 6:
            raise ValueError("daysOfWeek values must be 0-6")
        if parsed not in days:
            days.append(parsed)
    return sorted(days)


def normalize_countdown(item):
    if not item:
        return None
    if not isinstance(item, dict):
        raise ValueError("Countdown must be an object")
    label = str(item.get("label") or "Manca").strip() or "Manca"
    target = parse_datetime(item.get("to") or item.get("countdownTo"))
    return {
        "label": label[:48],
        "to": isoformat(target),
    }


def normalize_soccer(item):
    source = item if isinstance(item, dict) else {}
    competition = str(source.get("competition") or "SA").strip().upper() or "SA"
    return {
        "enabled": bool(source.get("enabled")),
        "competition": competition[:16],
    }


def active_announcement(state, current=None):
    announcements = active_announcements(state, current)
    return announcements[0] if announcements else None


def active_announcements(state, current=None):
    current = current or now()
    candidates = []
    for item in state.get("announcements") or []:
        occurrence = active_occurrence(item, current)
        if occurrence:
            candidates.append((parse_datetime(item["createdAt"]), item.get("id") or "", item, occurrence))
    if not candidates:
        return []
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [public_announcement(row[2], row[3]) for row in candidates]


def public_announcement(item, occurrence):
    return {
        "id": item.get("id"),
        "kind": item.get("kind") or "one-shot",
        "text": item.get("text"),
        "policy": ANNOUNCEMENT_POLICY,
        "createdAt": item.get("createdAt"),
        "startsAt": isoformat(occurrence["startsAt"]),
        "endsAt": isoformat(occurrence["endsAt"]),
    }


def active_occurrence(item, current):
    if item.get("kind") == "periodic":
        return active_periodic_occurrence(item, current)
    try:
        starts_at = parse_datetime(item.get("startsAt"))
        ends_at = parse_datetime(item.get("endsAt"))
    except Exception:
        return None
    if starts_at <= current < ends_at:
        return {"startsAt": starts_at, "endsAt": ends_at}
    return None


def active_periodic_occurrence(item, current):
    try:
        recurrence_starts_at = parse_datetime(item.get("recurrenceStartsAt"))
        recurrence_ends_at = parse_datetime(item.get("recurrenceEndsAt"))
        start_time = parse_time(item.get("startTime"))
    except Exception:
        return None

    if current < recurrence_starts_at or current >= recurrence_ends_at:
        return None

    candidates = [current.date(), (current - timedelta(days=1)).date()]
    for day in candidates:
        if not periodic_day_matches(item, day):
            continue
        starts_at = datetime.combine(day, start_time, timezone())
        ends_at = periodic_end_for(item, starts_at)
        if ends_at <= recurrence_starts_at or starts_at >= recurrence_ends_at:
            continue
        visible_start = max(starts_at, recurrence_starts_at)
        visible_end = min(ends_at, recurrence_ends_at)
        if visible_start <= current < visible_end:
            return {"startsAt": visible_start, "endsAt": visible_end}
    return None


def periodic_day_matches(item, day):
    days = item.get("daysOfWeek") or []
    if day.weekday() not in days:
        return False
    return item.get("frequency") in ("daily", "weekly")


def periodic_end_for(item, starts_at):
    if item.get("endTime"):
        parsed = parse_time(item.get("endTime"))
        ends_at = datetime.combine(starts_at.date(), parsed, timezone())
        if ends_at <= starts_at:
            ends_at = ends_at + timedelta(days=1)
        return ends_at
    return starts_at + timedelta(minutes=int(item.get("durationMinutes") or 0))


def active_countdown(state, current=None):
    current = current or now()
    countdown = state.get("countdown")
    if not countdown:
        return None
    try:
        target = parse_datetime(countdown.get("to"))
    except Exception:
        return None
    if target <= current:
        return None
    return {
        "label": countdown.get("label") or "Manca",
        "to": isoformat(target),
    }


async def public_state():
    state = load_state()
    current = now()
    announcements = active_announcements(state, current)
    response = {
        "visible": bool(state.get("visible")),
        "color": normalize_color(state.get("color") or DEFAULT_COLOR),
        "announcement": announcements[0] if announcements else None,
        "announcements": announcements,
        "countdown": active_countdown(state, current),
        "soccer": await public_soccer(state),
        "updatedAt": state.get("updatedAt") or isoformat(current),
    }
    return response


async def public_soccer(state):
    soccer_state = state.get("soccer") or {}
    if not soccer_state.get("enabled"):
        return {
            "enabled": False,
            "available": False,
            "competition": soccer_state.get("competition") or "SA",
            "label": "",
            "items": [],
            "message": "Soccer disabled",
        }
    try:
        from app.services import soccer

        return await soccer.load_compact(soccer_state.get("competition") or "SA")
    except Exception as error:
        return {
            "enabled": True,
            "available": False,
            "competition": soccer_state.get("competition") or "SA",
            "label": soccer_state.get("competition") or "Soccer",
            "items": [],
            "message": str(error) or "Soccer unavailable",
        }


def set_visible(visible):
    def mutate(state):
        state["visible"] = bool(visible)

    return update_state(mutate)


def set_color(value):
    color = normalize_color(value)

    def mutate(state):
        state["color"] = color

    return update_state(mutate)


def add_one_shot_announcement(text, starts_at, ends_at):
    item = normalize_announcement(
        {
            "kind": "one-shot",
            "text": text,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "createdAt": now(),
        }
    )

    def mutate(state):
        state["announcements"].append(item)
        state["visible"] = True

    return update_state(mutate)


def add_periodic_announcement(text, frequency, days_of_week, start_time, recurrence_ends_at, end_time=None, duration_minutes=None):
    item = normalize_announcement(
        {
            "kind": "periodic",
            "text": text,
            "frequency": frequency,
            "daysOfWeek": days_of_week,
            "startTime": start_time,
            "endTime": end_time,
            "durationMinutes": duration_minutes,
            "recurrenceEndsAt": recurrence_ends_at,
            "createdAt": now(),
        }
    )

    def mutate(state):
        state["announcements"].append(item)
        state["visible"] = True

    return update_state(mutate)


def announcement_records(current=None):
    state = load_state()
    current = current or now()
    records = [announcement_record(item, current) for item in state.get("announcements") or []]
    records.sort(key=lambda item: (parse_datetime(item["createdAt"]), item["id"]), reverse=True)
    return records


def announcement_record(item, current):
    occurrence = active_occurrence(item, current)
    record = {
        "id": item.get("id") or "",
        "kind": item.get("kind") or "one-shot",
        "text": item.get("text") or "",
        "createdAt": item.get("createdAt"),
        "active": bool(occurrence),
        "activeStartsAt": isoformat(occurrence["startsAt"]) if occurrence else None,
        "activeEndsAt": isoformat(occurrence["endsAt"]) if occurrence else None,
    }
    if record["kind"] == "periodic":
        record.update(
            {
                "frequency": item.get("frequency"),
                "daysOfWeek": item.get("daysOfWeek") or [],
                "startTime": item.get("startTime"),
                "endTime": item.get("endTime"),
                "durationMinutes": item.get("durationMinutes"),
                "recurrenceStartsAt": item.get("recurrenceStartsAt"),
                "recurrenceEndsAt": item.get("recurrenceEndsAt"),
            }
        )
    else:
        record.update(
            {
                "startsAt": item.get("startsAt"),
                "endsAt": item.get("endsAt"),
            }
        )
    return record


def delete_announcement(announcement_id):
    target = str(announcement_id or "").strip()
    deleted = {"value": False}

    def mutate(state):
        kept = []
        for item in state.get("announcements") or []:
            if str(item.get("id") or "") == target:
                deleted["value"] = True
            else:
                kept.append(item)
        state["announcements"] = kept

    update_state(mutate)
    return deleted["value"]


def clear_announcements():
    def mutate(state):
        state["announcements"] = []

    return update_state(mutate)


def set_countdown(label, target):
    countdown = normalize_countdown({"label": label, "to": target})

    def mutate(state):
        state["countdown"] = countdown
        state["visible"] = True

    return update_state(mutate)


def clear_countdown():
    def mutate(state):
        state["countdown"] = None

    return update_state(mutate)


def set_soccer_enabled(enabled):
    def mutate(state):
        state["soccer"]["enabled"] = bool(enabled)
        if enabled:
            state["visible"] = True

    return update_state(mutate)


def set_soccer_competition(competition):
    normalized = normalize_soccer({"enabled": True, "competition": competition})

    def mutate(state):
        state["soccer"]["enabled"] = True
        state["soccer"]["competition"] = normalized["competition"]
        state["visible"] = True

    return update_state(mutate)
