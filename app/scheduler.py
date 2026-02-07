from __future__ import annotations
import re
import calendar
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

SHIFT_LABELS = {
    "E": "早番",
    "D": "日勤",
    "S": "準夜",
    "N": "夜勤",
}

SHIFT_KEYS = ["E", "D", "S", "N"]


@dataclass
class PersonRule:
    allowed_shifts: Optional[Set[str]] = None
    weekend_off: bool = False
    weekly_max: Optional[int] = None


def parse_month(month_text: str) -> Tuple[int, int]:
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月", month_text)
    if not m:
        raise ValueError("対象月の形式が不正です。例: 2026年4月")
    return int(m.group(1)), int(m.group(2))


def month_days(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def split_tokens(text: str) -> List[str]:
    parts = re.split(r"[\n、,;]", text)
    return [p.strip() for p in parts if p.strip()]


def extract_day(token: str) -> Optional[int]:
    # Accept formats: 4/12, 4月12日, 12日, 12
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", token)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", token)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d{1,2})\s*日", token)
    if m:
        return int(m.group(1))
    m = re.match(r"^(\d{1,2})\b", token)
    if m:
        return int(m.group(1))
    return None


def parse_allowed_shifts(token: str) -> Optional[Set[str]]:
    token = token.replace("　", " ")
    token = token.replace("／", "/")
    allowed: Set[str] = set()

    if "休み" in token or "年休" in token or "×" in token:
        # If only休み/年休 specified, treat as off (None)
        # If combined with shifts, we keep shift choices (user expects OR)
        if any(k in token for k in ["早番", "日勤", "準夜", "夜勤", "○", "ー", "☆", "●"]):
            pass
        else:
            return set()

    if "出張" in token:
        # treat as off for scheduling
        if any(k in token for k in ["早番", "日勤", "準夜", "夜勤", "○", "ー", "☆", "●"]):
            pass
        else:
            return set()

    if "早番" in token or "○" in token:
        allowed.add("E")
    if "日勤" in token or "ー" in token:
        allowed.add("D")
    if "準夜" in token or "☆" in token:
        allowed.add("S")
    if "夜勤" in token or "●" in token:
        allowed.add("N")

    if "早番のみ" in token:
        return {"E"}
    if "日勤のみ" in token:
        return {"D"}
    if "準夜のみ" in token:
        return {"S"}
    if "夜勤のみ" in token:
        return {"N"}

    return allowed if allowed else None


def parse_requests(month_text: str, requests: List[dict]) -> Dict[str, Dict[int, Optional[Set[str]]]]:
    allowed_map: Dict[str, Dict[int, Optional[Set[str]]]] = {}
    for r in requests:
        doctor = r["doctor"]
        text = r.get("request_text", "")
        if "/ 備考:" in text:
            text = text.split("/ 備考:", 1)[0]
        allowed_map.setdefault(doctor, {})
        for token in split_tokens(text):
            day = extract_day(token)
            if not day:
                continue
            shifts = parse_allowed_shifts(token)
            if shifts is None:
                continue
            # If already exists, merge
            if day in allowed_map[doctor] and allowed_map[doctor][day] is not None:
                if shifts:
                    allowed_map[doctor][day] = set(allowed_map[doctor][day]) | set(shifts)
                else:
                    allowed_map[doctor][day] = set()
            else:
                allowed_map[doctor][day] = shifts
    return allowed_map


def parse_individual_rules(lines: List[str], staff_list: List[str]) -> Dict[str, PersonRule]:
    rules: Dict[str, PersonRule] = {s: PersonRule() for s in staff_list}
    for line in lines:
        for name in staff_list:
            if name not in line:
                continue
            rule = rules[name]
            if "土日" in line and "休" in line:
                rule.weekend_off = True
            m = re.search(r"週\s*(\d+)\s*回", line)
            if m:
                rule.weekly_max = int(m.group(1))
            if "早番/日勤のみ" in line or "早番もしくは日勤のみ" in line:
                rule.allowed_shifts = {"E", "D"}
            if "夜勤のみ" in line:
                rule.allowed_shifts = {"N"}
    return rules


HOLIDAYS_2026 = {
    date(2026, 1, 1),
    date(2026, 1, 12),
    date(2026, 2, 11),
    date(2026, 2, 23),
    date(2026, 3, 20),
    date(2026, 4, 29),
    date(2026, 5, 3),
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 5, 6),  # Substitute holiday for Constitution Memorial Day
    date(2026, 7, 20),
    date(2026, 8, 11),
    date(2026, 9, 21),
    date(2026, 9, 22),  # Bridge holiday
    date(2026, 9, 23),
    date(2026, 10, 12),
    date(2026, 11, 3),
    date(2026, 11, 23),
}


def is_holiday(d: date) -> bool:
    if d.year == 2026:
        return d in HOLIDAYS_2026
    return False


def weekday_shifts(d: date) -> List[str]:
    if is_weekend(d) or is_holiday(d):
        return ["E", "S", "N"]
    return ["E", "D", "S", "N"]


def can_assign(
    name: str,
    shift: str,
    day: int,
    d: date,
    allowed_map: Dict[str, Dict[int, Optional[Set[str]]]],
    rules: Dict[str, PersonRule],
    last_shift: Dict[str, Optional[str]],
    cons_work: Dict[str, int],
    cons_shift: Dict[str, int],
    weekly_count: Dict[Tuple[str, int], int],
) -> bool:
    # Availability
    if name in allowed_map and day in allowed_map[name]:
        allowed = allowed_map[name][day]
        if allowed is not None and shift not in allowed:
            return False
        if allowed is not None and len(allowed) == 0:
            return False
    # Personal rules
    rule = rules.get(name, PersonRule())
    if rule.weekend_off and is_weekend(d):
        return False
    if rule.allowed_shifts and shift not in rule.allowed_shifts:
        return False

    # Consecutive work days
    if cons_work.get(name, 0) >= 5:
        return False

    # After shift constraints
    prev = last_shift.get(name)
    if prev == "S" and shift not in {"S", "N"}:
        return False
    if prev == "N" and shift != "N":
        return False

    # Consecutive shift limits
    if shift == prev and cons_shift.get(name, 0) >= 2:
        return False

    # Weekly max
    if rule.weekly_max is not None:
        week_key = (name, d.isocalendar().week)
        if weekly_count.get(week_key, 0) >= rule.weekly_max:
            return False

    return True


def score_candidate(
    name: str,
    shift: str,
    total_count: Dict[str, int],
    shift_count: Dict[Tuple[str, str], int],
    cons_work: Dict[str, int],
    last_shift: Dict[str, Optional[str]],
) -> float:
    score = 0.0
    score += total_count.get(name, 0)
    score += 0.8 * shift_count.get((name, shift), 0)
    if last_shift.get(name) == shift:
        score += 1.5
    score += 0.3 * cons_work.get(name, 0)
    return score


def generate_schedule(
    month_text: str,
    staff_list: List[str],
    requests: List[dict],
    individual_rules: List[str],
) -> Tuple[Dict[int, Dict[str, str]], Dict[str, Dict[str, int]]]:
    year, month = parse_month(month_text)
    days = month_days(year, month)
    allowed_map = parse_requests(month_text, requests)
    rules = parse_individual_rules(individual_rules, staff_list)

    schedule: Dict[int, Dict[str, str]] = {d: {} for d in range(1, days + 1)}
    last_shift: Dict[str, Optional[str]] = {s: None for s in staff_list}
    cons_shift: Dict[str, int] = {s: 0 for s in staff_list}
    cons_work: Dict[str, int] = {s: 0 for s in staff_list}
    total_count: Dict[str, int] = {s: 0 for s in staff_list}
    shift_count: Dict[Tuple[str, str], int] = {}
    weekly_count: Dict[Tuple[str, int], int] = {}

    for day in range(1, days + 1):
        d = date(year, month, day)
        required = weekday_shifts(d)
        # prioritize nights, then early, then day, then evening
        order = ["N", "E", "D", "S"]
        required_sorted = [s for s in order if s in required]

        assigned_today: Set[str] = set()
        for shift in required_sorted:
            candidates = []
            for name in staff_list:
                if name in assigned_today:
                    continue
                if not can_assign(
                    name,
                    shift,
                    day,
                    d,
                    allowed_map,
                    rules,
                    last_shift,
                    cons_work,
                    cons_shift,
                    weekly_count,
                ):
                    continue
                candidates.append(name)
            if not candidates:
                # Allow S to be empty, N try hard but allow empty
                schedule[day][shift] = ""
                continue
            # choose lowest score
            best = min(candidates, key=lambda n: score_candidate(n, shift, total_count, shift_count, cons_work, last_shift))
            schedule[day][shift] = best
            assigned_today.add(best)

        # Update per-person state after day assigned
        for name in staff_list:
            # Check if worked today
            worked_shift = None
            for sh in required_sorted:
                if schedule[day].get(sh) == name:
                    worked_shift = sh
                    break
            if worked_shift:
                total_count[name] += 1
                shift_count[(name, worked_shift)] = shift_count.get((name, worked_shift), 0) + 1
                week_key = (name, d.isocalendar().week)
                weekly_count[week_key] = weekly_count.get(week_key, 0) + 1

                if last_shift.get(name) == worked_shift:
                    cons_shift[name] = cons_shift.get(name, 0) + 1
                else:
                    cons_shift[name] = 1
                last_shift[name] = worked_shift
                cons_work[name] = cons_work.get(name, 0) + 1
            else:
                cons_work[name] = 0
                cons_shift[name] = 0
                last_shift[name] = None

    # Build counts
    counts: Dict[str, Dict[str, int]] = {s: {"E": 0, "D": 0, "S": 0, "N": 0} for s in staff_list}
    for day in range(1, days + 1):
        for sh, name in schedule[day].items():
            if name:
                counts[name][sh] += 1

    return schedule, counts


def render_table(month_text: str, schedule: Dict[int, Dict[str, str]]) -> str:
    year, month = parse_month(month_text)
    lines = []
    lines.append("| 日付 | 曜 | 早番 | 日勤 | 準夜 | 夜勤 |")
    lines.append("|---|---|---|---|---|---|")
    for day in sorted(schedule.keys()):
        d = date(year, month, day)
        wd = "月火水木金土日"[d.weekday()]
        e = schedule[day].get("E", "")
        dsh = schedule[day].get("D", "")
        s = schedule[day].get("S", "")
        n = schedule[day].get("N", "")
        lines.append(f"| {month}/{day} | {wd} | {e} | {dsh} | {s} | {n} |")
    return "\n".join(lines)


def render_counts(counts: Dict[str, Dict[str, int]]) -> str:
    lines = ["医師,早番,日勤,準夜,夜勤,合計"]
    for name, c in counts.items():
        total = c["E"] + c["D"] + c["S"] + c["N"]
        lines.append(f"{name},{c['E']},{c['D']},{c['S']},{c['N']},{total}")
    return "\n".join(lines)


def counts_from_table(table_text: str) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = {}
    for line in table_text.splitlines():
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if not parts:
            continue
        # Skip header/separator
        if parts[0] in {"日付", "---"}:
            continue
        if len(parts) < 6:
            continue
        # Expected: 日付, 曜, 早番, 日勤, 準夜, 夜勤
        e, d, s, n = parts[2], parts[3], parts[4], parts[5]
        for name, key in [(e, "E"), (d, "D"), (s, "S"), (n, "N")]:
            if not name or name in {"欠員", "空欄"}:
                continue
            counts.setdefault(name, {"E": 0, "D": 0, "S": 0, "N": 0})
            counts[name][key] += 1
    return counts
