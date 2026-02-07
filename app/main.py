from __future__ import annotations
from datetime import datetime
import json
from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import APP_NAME, STAFF_LIST, BASE_RULES, INDIVIDUAL_RULES, ADDITIONAL_RULES
from .db import (
    init_db,
    add_request,
    list_requests,
    list_requests_by_doctor,
    delete_request,
    upsert_travel,
    list_travel,
    get_travel,
    get_config_map,
    set_config_map,
    add_config_history,
    list_config_history,
    upsert_schedule,
    get_schedule,
    get_latest_schedule,
    export_all,
    restore_all,
)
from .scheduler import generate_schedule, render_table, render_counts, counts_from_table

app = FastAPI(title=APP_NAME)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_month_choices() -> list[str]:
    today = datetime.now()
    y = today.year
    m = today.month + 1
    choices = []
    for i in range(3):
        mm = m + i
        yy = y + (mm - 1) // 12
        mm = ((mm - 1) % 12) + 1
        choices.append(f"{yy}年{mm}月")
    return choices


def load_config() -> dict:
    stored = get_config_map()
    staff_list = stored.get("staff_list", ",".join(STAFF_LIST)).split(",")
    base_rules = stored.get("base_rules", "\n".join(BASE_RULES)).splitlines()
    individual_rules = stored.get("individual_rules", "\n".join(INDIVIDUAL_RULES)).splitlines()
    additional_rules = stored.get("additional_rules", "\n".join(ADDITIONAL_RULES)).splitlines()
    staff_list = [s.strip() for s in staff_list if s.strip()]
    base_rules = [s.strip() for s in base_rules if s.strip()]
    individual_rules = [s.strip() for s in individual_rules if s.strip()]
    additional_rules = [s.strip() for s in additional_rules if s.strip()]
    return {
        "staff_list": staff_list,
        "base_rules": base_rules,
        "individual_rules": individual_rules,
        "additional_rules": additional_rules,
    }


def build_prompt(month: str, requests: list[dict], cfg: dict) -> str:
    lines: list[str] = []
    lines.append("【対象月】")
    lines.append(month)
    lines.append("")
    lines.append("【スタッフ一覧】")
    lines.append("、".join(cfg["staff_list"]))
    lines.append("")
    lines.append("【基本ルール（固定）】")
    for r in cfg["base_rules"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("【個別制約（固定）】")
    for r in cfg["individual_rules"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("【追加ルール（固定）】")
    for r in cfg["additional_rules"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("【希望一覧】")
    if requests:
        for req in requests:
            lines.append(f"{req['doctor']}：{req['request_text']}")
    else:
        lines.append("（まだ希望が登録されていません）")
    lines.append("")
    lines.append("【出張日数／出張日】")
    travel_rows = list_travel(month)
    if travel_rows:
        for t in travel_rows:
            day_part = f"{t['days']}日" if t.get("days") is not None else "未入力"
            date_part = t.get("dates_text") or "未入力"
            lines.append(f"{t['doctor']}：日数={day_part}、日付={date_part}")
    else:
        lines.append("（まだ登録されていません）")
    lines.append("")
    lines.append("【斉藤 夜勤固定】")
    lines.append("（ここに日付を入力してください）")
    return "\n".join(lines)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": APP_NAME,
        },
    )


@app.get("/input", response_class=HTMLResponse)
def input_page(request: Request, month: str | None = None, doctor: str | None = None):
    cfg = load_config()
    month_value = month or ""
    doctor_value = doctor or ""
    month_choices = get_month_choices()
    my_requests = []
    my_travel = None
    if month_value and doctor_value:
        my_requests = list_requests_by_doctor(month_value, doctor_value)
        my_travel = get_travel(month_value, doctor_value)
    return templates.TemplateResponse(
        "input.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "staff_list": cfg["staff_list"],
            "month": month_value,
            "doctor": doctor_value,
            "month_choices": month_choices,
            "my_requests": my_requests,
            "my_travel": my_travel,
        },
    )


@app.post("/input")
def submit_request(
    month: str = Form(...),
    doctor: str = Form(...),
    request_text: str = Form(...),
    request_note: str = Form(""),
):
    month_value = month.strip()
    doctor_value = doctor.strip()
    note = request_note.strip()
    text = request_text.strip()
    if note:
        text = f"{text} / 備考: {note}"
    add_request(month=month_value, doctor=doctor_value, request_text=text, created_at=now_str())
    return RedirectResponse(url=f"/input?month={month_value}&doctor={doctor_value}", status_code=303)


@app.post("/input/travel")
def submit_travel(
    month: str = Form(...),
    doctor: str = Form(...),
    travel_days: str = Form(""),
    travel_dates: str = Form(""),
):
    month_value = month.strip()
    doctor_value = doctor.strip()
    days_value = None
    if travel_days.strip():
        try:
            days_value = int(travel_days.strip())
        except ValueError:
            days_value = None
    dates_value = travel_dates.strip() or None
    upsert_travel(
        month=month_value,
        doctor=doctor_value,
        days=days_value,
        dates_text=dates_value,
        created_at=now_str(),
    )
    return RedirectResponse(url=f"/input?month={month_value}&doctor={doctor_value}", status_code=303)


@app.post("/input/delete")
def delete_request_item(request_id: int = Form(...), month: str = Form(...), doctor: str = Form(...)):
    delete_request(int(request_id))
    return RedirectResponse(url=f"/input?month={month}&doctor={doctor}", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, month: str | None = None):
    cfg = load_config()
    month_value = month or ""
    month_choices = get_month_choices()
    reqs = list_requests(month_value) if month_value else []
    prompt = build_prompt(month_value, reqs, cfg) if month_value else ""
    draft = get_schedule(month_value, "draft") if month_value else None
    final = get_schedule(month_value, "final") if month_value else None
    travel_rows = list_travel(month_value) if month_value else []
    submitted = {r["doctor"] for r in reqs}
    missing = [name for name in cfg["staff_list"] if name not in submitted]
    error = request.query_params.get("error", "")
    config_error = request.query_params.get("config_error", "")
    history = list_config_history(30)
    csv_url = f"/admin/export.csv?month={month_value}" if month_value else ""
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "month": month_value,
            "requests": reqs,
            "prompt": prompt,
            "draft": draft,
            "final": final,
            "travel_rows": travel_rows,
            "missing": missing,
            "error": error,
            "config": cfg,
            "config_error": config_error,
            "history": history,
            "month_choices": month_choices,
            "csv_url": csv_url,
        },
    )


@app.get("/admin/export.csv")
def export_requests_csv(month: str):
    reqs = list_requests(month)
    lines = ["月,氏名,希望"]
    for r in reqs:
        text = r.get("request_text", "").replace("\n", " ")
        lines.append(f"{month},{r['doctor']},{text}")
    content = "\n".join(lines)
    return HTMLResponse(content=content, media_type="text/csv; charset=utf-8")


@app.get("/admin/backup.json")
def export_backup():
    payload = {
        "version": 1,
        "exported_at": now_str(),
        "data": export_all(),
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"och-shiftkun-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return Response(content=content, media_type="application/json; charset=utf-8", headers=headers)


@app.post("/admin/restore")
def restore_backup(file: UploadFile = File(...)):
    try:
        raw = file.file.read()
        payload = json.loads(raw.decode("utf-8"))
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            raise ValueError("invalid payload")
        restore_all(data)
    except Exception:
        return RedirectResponse(url="/backup?restore=fail", status_code=303)
    return RedirectResponse(url="/backup?restore=ok", status_code=303)


@app.get("/backup", response_class=HTMLResponse)
def backup_page(request: Request):
    restore_status = request.query_params.get("restore", "")
    return templates.TemplateResponse(
        "backup.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "restore_status": restore_status,
        },
    )


@app.post("/admin/generate")
def generate_schedule_action(month: str = Form(...)):
    cfg = load_config()
    month_value = month.strip()
    reqs = list_requests(month_value)
    schedule, counts = generate_schedule(
        month_text=month_value,
        staff_list=cfg["staff_list"],
        requests=reqs,
        individual_rules=cfg["individual_rules"],
    )
    table_text = render_table(month_value, schedule)
    counts_text = render_counts(counts)
    upsert_schedule(
        month=month_value,
        status="draft",
        table_text=table_text,
        counts_text=counts_text,
        change_log="自動生成（下書き）",
        created_at=now_str(),
    )
    return RedirectResponse(url=f"/admin?month={month_value}", status_code=303)


@app.post("/admin/config")
def save_config(
    staff_list: str = Form(...),
    base_rules: str = Form(...),
    individual_rules: str = Form(...),
    additional_rules: str = Form(...),
    editor: str = Form(""),
    month: str = Form(""),
):
    # Normalize input
    staff_raw = staff_list.replace("、", ",").strip()
    staff_items = [s.strip() for s in staff_raw.split(",") if s.strip()]
    if not staff_items:
        return RedirectResponse(url=f"/admin?month={month}&config_error=staff_empty", status_code=303)
    if len(set(staff_items)) != len(staff_items):
        return RedirectResponse(url=f"/admin?month={month}&config_error=staff_dup", status_code=303)

    base_raw = base_rules.strip()
    indiv_raw = individual_rules.strip()
    add_raw = additional_rules.strip()
    if not base_raw:
        return RedirectResponse(url=f"/admin?month={month}&config_error=base_empty", status_code=303)
    if not indiv_raw:
        return RedirectResponse(url=f"/admin?month={month}&config_error=indiv_empty", status_code=303)
    if not add_raw:
        return RedirectResponse(url=f"/admin?month={month}&config_error=add_empty", status_code=303)
    if not editor.strip():
        return RedirectResponse(url=f"/admin?month={month}&config_error=editor_empty", status_code=303)

    current = load_config()
    add_config_history(
        staff_list=",".join(current["staff_list"]),
        base_rules="\n".join(current["base_rules"]),
        individual_rules="\n".join(current["individual_rules"]),
        additional_rules="\n".join(current["additional_rules"]),
        created_at=now_str(),
        editor=editor.strip(),
    )
    set_config_map(
        {
            "staff_list": ",".join(staff_items),
            "base_rules": base_raw,
            "individual_rules": indiv_raw,
            "additional_rules": add_raw,
        }
    )
    return RedirectResponse(url=f"/admin?month={month}", status_code=303)


@app.post("/admin/save")
def save_schedule(
    month: str = Form(...),
    table_text: str = Form(...),
    counts_text: str = Form(...),
    change_log: str = Form(""),
    save_type: str = Form("draft"),
):
    month_value = month.strip()
    reqs = list_requests(month_value)
    submitted = {r["doctor"] for r in reqs}
    missing = [name for name in STAFF_LIST if name not in submitted]
    if save_type == "final" and missing:
        return RedirectResponse(url=f"/admin?month={month_value}&error=missing", status_code=303)
    counts_value = counts_text.strip()
    if not counts_value:
        counts_value = render_counts(counts_from_table(table_text.strip()))
    upsert_schedule(
        month=month_value,
        status=save_type,
        table_text=table_text.strip(),
        counts_text=counts_value,
        change_log=change_log.strip(),
        created_at=now_str(),
    )
    return RedirectResponse(url=f"/admin?month={month_value}", status_code=303)


@app.get("/view", response_class=HTMLResponse)
def view_page(request: Request, month: str | None = None):
    month_value = month or ""
    month_choices = get_month_choices()
    schedule = None
    if month_value:
        schedule = get_schedule(month_value, "final") or get_latest_schedule(month_value)
    travel_rows = list_travel(month_value) if month_value else []
    travel_map = {t["doctor"]: (t.get("days") or 0) for t in travel_rows}
    if month_value and not travel_rows:
        # Fallback: derive travel count from requests if travel table is unused
        reqs = list_requests(month_value)
        for r in reqs:
            text = r.get("request_text", "")
            # Ignore notes after separator
            if "/ 備考:" in text:
                text = text.split("/ 備考:", 1)[0]
            count = text.count("出張")
            travel_map[r["doctor"]] = travel_map.get(r["doctor"], 0) + count
    counts_with_travel = []
    if schedule and schedule.get("counts_text"):
        lines = [l.strip() for l in schedule["counts_text"].splitlines() if l.strip()]
        for line in lines:
            if line.startswith("医師") or line.startswith("医者") or line.startswith("スタッフ"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            name = parts[0]
            try:
                total = int(parts[5])
            except ValueError:
                continue
            travel_days = int(travel_map.get(name, 0))
            counts_with_travel.append(
                {
                    "doctor": name,
                    "total": total,
                    "travel": travel_days,
                    "total_with_travel": total + travel_days,
                }
            )
    return templates.TemplateResponse(
        "view.html",
        {
            "request": request,
            "app_name": APP_NAME,
            "month": month_value,
            "month_choices": month_choices,
            "schedule": schedule,
            "counts_with_travel": counts_with_travel,
        },
    )
