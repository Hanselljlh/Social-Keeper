from pathlib import Path
import calendar
import csv
import io
import os
import re
import secrets
import shutil
import zipfile
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, create_engine, or_, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
VERSION_FILE = ROOT_DIR / "VERSION"

RUNTIME_ROOT = Path("/app/runtime")
DB_PATH = RUNTIME_ROOT / "database" / "social_keeper.db"
UPLOADS_ROOT = RUNTIME_ROOT / "uploads"
EXPORTS_ROOT = RUNTIME_ROOT / "exports"
CONFIG_ROOT = RUNTIME_ROOT / "config"
LOGS_ROOT = RUNTIME_ROOT / "logs"

for folder in [DB_PATH.parent, UPLOADS_ROOT, EXPORTS_ROOT, CONFIG_ROOT, LOGS_ROOT]:
    folder.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(100))
    distance: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    age: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    red_flags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    green_flags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    boundaries: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reminders: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    profile_parser_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversation_thread: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reminder_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    initial_review_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    uploads: Mapped[list["UploadItem"]] = relationship(back_populates="person", cascade="all, delete-orphan")

    @property
    def display_name(self) -> str:
        age_value = self.age if self.age else "??"
        return f"{self.app_name} - {self.name} - {self.location} - {age_value}"


class UploadItem(Base):
    __tablename__ = "upload_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    upload_category: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    upload_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Person] = relationship(back_populates="uploads")


class SettingOption(Base):
    __tablename__ = "setting_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(engine)


def ensure_column(table_name: str, column_name: str, definition: str) -> None:
    with engine.begin() as connection:
        columns = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        existing = {column[1] for column in columns}
        if column_name not in existing:
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


ensure_column("people", "review_overview", "TEXT")
ensure_column("people", "profile_parser_output", "TEXT")
ensure_column("people", "conversation_thread", "TEXT")
ensure_column("people", "distance", "TEXT")
ensure_column("upload_items", "upload_note", "TEXT")
ensure_column("people", "reminder_date", "DATE")
ensure_column("upload_items", "upload_category", "TEXT")
ensure_column("upload_items", "extracted_text", "TEXT")
ensure_column("setting_options", "sort_order", "INTEGER")

app = FastAPI(title=os.getenv("APP_NAME", "Social Keeper"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=UPLOADS_ROOT), name="media")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

STATUS_OPTIONS = ["New", "Talking", "Follow Up", "Date Planned", "Met", "Paused", "Closed"]
UPLOAD_CATEGORIES = {
    "profile_intake": "Profile screenshots and copied text",
    "general_photos": "General photos",
    "message_tracking": "Message tracking",
}


def app_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def get_setting_values(db: Session, kind: str, fallback: list[str]) -> list[str]:
    values = [item.value for item in get_setting_options(db, kind)]
    return values or fallback


def get_setting_options(db: Session, kind: str) -> list[SettingOption]:
    return (
        db.query(SettingOption)
        .filter(SettingOption.kind == kind)
        .order_by(SettingOption.sort_order.asc().nullslast(), SettingOption.value.asc())
        .all()
    )


def next_sort_order(db: Session, kind: str) -> int:
    existing = get_setting_options(db, kind)
    if not existing:
        return 1
    return max((item.sort_order or 0) for item in existing) + 1


def sort_profile_tags(person: Person, tag_options: list[SettingOption]) -> list[str]:
    current_tags = parse_tags(person.tags)
    if not current_tags:
        return []
    priority = {option.value.lower(): option.sort_order or 9999 for option in tag_options}
    return sorted(
        current_tags,
        key=lambda tag: (priority.get(tag.lower(), 9999), tag.lower()),
    )


def is_logged_in(request: Request) -> bool:
    return request.cookies.get("session") == os.getenv("SECRET_KEY", "")


def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)
    return None


def get_db() -> Session:
    return SessionLocal()


def build_review_overview(person: Person) -> str:
    lines = [
        f"Record: {person.display_name}",
        f"Status: {person.status or 'New'}",
        f"Phone / WhatsApp: {person.phone or 'Not provided'}",
        f"Tags: {person.tags or 'None'}",
        f"Summary: {person.summary or 'No summary yet'}",
        f"Green Flags: {person.green_flags or 'None noted'}",
        f"Red Flags: {person.red_flags or 'None noted'}",
        f"Boundaries: {person.boundaries or 'None noted'}",
        f"Follow-up Reminders: {person.reminders or 'None noted'}",
        f"Reminder Date: {person.reminder_date.isoformat() if person.reminder_date else 'Not set'}",
    ]
    return "\n".join(lines)


def upload_groups(person: Person) -> dict[str, list[UploadItem]]:
    grouped = {key: [] for key in UPLOAD_CATEGORIES}
    for item in sorted(person.uploads, key=lambda entry: entry.created_at, reverse=True):
        grouped[item.upload_category or "profile_intake"].append(item)
    return grouped


def parse_tags(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


def read_text_file(path: Path) -> str:
    for encoding in ["utf-8", "utf-8-sig", "latin-1"]:
        try:
            return path.read_text(encoding=encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


def upload_text_content(item: UploadItem) -> str:
    if item.extracted_text and item.extracted_text.strip():
        return item.extracted_text.strip()
    source = UPLOADS_ROOT / item.stored_name
    if source.suffix.lower() == ".txt" and source.exists():
        return read_text_file(source)
    return ""


def normalize_text_lines(value: str) -> list[str]:
    cleaned = re.sub(r"\r\n?", "\n", value)
    lines = []
    seen: set[str] = set()
    for raw_line in cleaned.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip(" -\t")
        if len(line) < 2:
            continue
        lowered = line.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(line)
    return lines


def collect_upload_text(person: Person, category: str) -> list[dict[str, str]]:
    collected: list[dict[str, str]] = []
    for item in person.uploads:
        if (item.upload_category or "profile_intake") != category:
            continue
        text_value = upload_text_content(item)
        if not text_value and not item.upload_note:
            continue
        collected.append(
            {
                "name": item.original_name,
                "note": item.upload_note or "",
                "text": text_value,
            }
        )
    return collected


def build_profile_intake_parser(person: Person) -> tuple[str, str]:
    source_items = collect_upload_text(person, "profile_intake")
    all_lines: list[str] = []
    for item in source_items:
        if item["note"]:
            all_lines.extend(normalize_text_lines(item["note"]))
        if item["text"]:
            all_lines.extend(normalize_text_lines(item["text"]))

    keyword_map = {
        "work": "Work",
        "job": "Work",
        "school": "School",
        "college": "School",
        "university": "School",
        "bio": "Bio",
        "about": "Bio",
        "looking for": "Looking For",
        "height": "Height",
        "kids": "Kids",
        "smoke": "Smoking",
        "drink": "Drinking",
        "religion": "Religion",
        "christian": "Religion",
        "muslim": "Religion",
        "hobby": "Interests",
        "interest": "Interests",
        "love": "Interests",
        "like": "Interests",
    }
    fact_buckets: dict[str, list[str]] = {}
    for line in all_lines:
        lower_line = line.lower()
        for keyword, label in keyword_map.items():
            if keyword in lower_line:
                fact_buckets.setdefault(label, [])
                if line not in fact_buckets[label]:
                    fact_buckets[label].append(line)

    bio_lines = all_lines[:10]
    summary_parts = []
    if bio_lines:
        summary_parts.append(" ".join(bio_lines[:4]))
        if len(bio_lines) > 4:
            summary_parts.append(" ".join(bio_lines[4:8]))
    summary_text = "\n\n".join(part.strip() for part in summary_parts if part.strip())

    parser_lines = [
        f"Profile Intake Parser for {person.display_name}",
        f"Source Files: {len(source_items)}",
        "",
        "Bio Draft",
        summary_text or "No enough copied text yet. Add more profile text or fill extracted text on uploads.",
        "",
        "Structured Facts",
    ]
    if fact_buckets:
        for label in sorted(fact_buckets):
            parser_lines.append(f"{label}:")
            for line in fact_buckets[label][:5]:
                parser_lines.append(f"- {line}")
    else:
        parser_lines.append("- No structured facts found yet.")

    if source_items:
        parser_lines.extend(["", "Sources"])
        for item in source_items:
            source_note = f" | {item['note']}" if item["note"] else ""
            parser_lines.append(f"- {item['name']}{source_note}")

    return summary_text, "\n".join(parser_lines).strip()


def build_conversation_parser(person: Person) -> str:
    source_items = collect_upload_text(person, "message_tracking")
    sections = [f"Conversation Thread for {person.display_name}", ""]
    if not source_items:
        sections.append("No message tracking text yet. Upload .txt files or paste screenshot text into extracted text.")
        return "\n".join(sections).strip()

    for index, item in enumerate(source_items, start=1):
        header_parts = [f"{index}. {item['name']}"]
        if item["note"]:
            header_parts.append(item["note"])
        sections.append(" | ".join(header_parts))
        text_value = item["text"].strip()
        if not text_value:
            sections.append("[No copied or extracted text yet]")
        else:
            lines = normalize_text_lines(text_value)
            if not lines:
                sections.append("[No readable message lines found]")
            else:
                for line in lines:
                    sections.append(line)
        sections.append("")
    return "\n".join(sections).strip()


def apply_person_filters(db: Session, filters: dict[str, str]) -> list[Person]:
    query = db.query(Person)
    search = filters.get("search", "").strip()
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Person.app_name.ilike(like),
                Person.name.ilike(like),
                Person.location.ilike(like),
                Person.age.ilike(like),
                Person.status.ilike(like),
                Person.tags.ilike(like),
                Person.phone.ilike(like),
            )
        )

    for field in ["app_name", "name", "location", "distance", "age", "status", "tags"]:
        value = filters.get(field, "").strip()
        if value:
            query = query.filter(getattr(Person, field).ilike(f"%{value}%"))

    return query.order_by(Person.created_at.desc()).all()


def find_duplicates(people: list[Person]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for index, person in enumerate(people):
        for other in people[index + 1:]:
            reasons: list[str] = []
            if person.name.strip().lower() == other.name.strip().lower():
                reasons.append("same name")
            if person.phone and other.phone and person.phone.strip() == other.phone.strip():
                reasons.append("same phone")
            if person.location.strip().lower() == other.location.strip().lower() and person.name[:1].lower() == other.name[:1].lower():
                reasons.append("similar name and location")
            if reasons:
                results.append({"left": person, "right": other, "reasons": ", ".join(reasons)})
    return results


def build_reminder_groups(people: list[Person]) -> dict[str, list[Person]]:
    groups = {
        "today": [],
        "this_week": [],
        "later": [],
        "unscheduled": [],
    }
    today = datetime.utcnow().date()
    week_end = today.toordinal() + 7
    for person in people:
        if not person.reminder_date:
            groups["unscheduled"].append(person)
        elif person.reminder_date <= today:
            groups["today"].append(person)
        elif person.reminder_date.toordinal() <= week_end:
            groups["this_week"].append(person)
        else:
            groups["later"].append(person)
    return groups


def build_calendar_month(people: list[Person], year: int | None = None, month: int | None = None) -> dict[str, object]:
    today = datetime.utcnow().date()
    year = year or today.year
    month = month or today.month
    first_weekday, days_in_month = calendar.monthrange(year, month)
    people_by_day: dict[date, list[Person]] = {}
    for person in people:
        if person.reminder_date and person.reminder_date.year == year and person.reminder_date.month == month:
            people_by_day.setdefault(person.reminder_date, []).append(person)

    weeks: list[list[dict[str, object]]] = []
    week: list[dict[str, object]] = [{"date": None, "people": []} for _ in range(first_weekday)]
    for day_number in range(1, days_in_month + 1):
        day_date = date(year, month, day_number)
        week.append({"date": day_date, "people": people_by_day.get(day_date, [])})
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        week.extend({"date": None, "people": []} for _ in range(7 - len(week)))
        weeks.append(week)

    return {
        "label": f"{calendar.month_name[month]} {year}",
        "year": year,
        "month": month,
        "weekday_labels": [calendar.day_abbr[index] for index in range(7)],
        "weeks": weeks,
    }


def build_profiles_csv(people: list[Person]) -> str:
    output = io.StringIO()
    fieldnames = [
        "app_name",
        "name",
        "location",
        "distance",
        "age",
        "phone",
        "status",
        "tags",
        "reminder_date",
        "summary",
        "notes",
        "red_flags",
        "green_flags",
        "boundaries",
        "reminders",
        "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for person in people:
        writer.writerow(
            {
                "app_name": person.app_name,
                "name": person.name,
                "location": person.location,
                "distance": person.distance or "",
                "age": person.age or "",
                "phone": person.phone or "",
                "status": person.status or "New",
                "tags": person.tags or "",
                "reminder_date": person.reminder_date.isoformat() if person.reminder_date else "",
                "summary": person.summary or "",
                "notes": person.notes or "",
                "red_flags": person.red_flags or "",
                "green_flags": person.green_flags or "",
                "boundaries": person.boundaries or "",
                "reminders": person.reminders or "",
                "created_at": person.created_at.isoformat() if person.created_at else "",
            }
        )
    return output.getvalue()


def build_full_backup(db_path: Path = DB_PATH, uploads_root: Path = UPLOADS_ROOT, exports_root: Path = EXPORTS_ROOT, backup_root: Path | None = None) -> Path:
    backup_root = backup_root or (EXPORTS_ROOT / "backups")
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_path = backup_root / f"social-keeper-backup-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if db_path.exists():
            archive.write(db_path, arcname=f"database/{db_path.name}")
        for root, _, files in os.walk(uploads_root):
            for filename in files:
                source = Path(root) / filename
                archive.write(source, arcname=f"uploads/{source.relative_to(uploads_root)}")
        for root, _, files in os.walk(exports_root):
            for filename in files:
                source = Path(root) / filename
                if source == backup_path:
                    continue
                archive.write(source, arcname=f"exports/{source.relative_to(exports_root)}")
    return backup_path


def seed_demo_data() -> None:
    with SessionLocal() as db:
        if db.query(SettingOption).count() == 0:
            for index, option in enumerate(STATUS_OPTIONS, start=1):
                db.add(SettingOption(kind="status", value=option, sort_order=index))
            for index, option in enumerate(["local", "follow-up", "verified", "favourite"], start=1):
                db.add(SettingOption(kind="tag", value=option, sort_order=index))
            db.commit()
        else:
            changed = False
            for kind in ["status", "tag"]:
                for index, option in enumerate(get_setting_options(db, kind), start=1):
                    if option.sort_order != index:
                        option.sort_order = index
                        changed = True
            if changed:
                db.commit()

        if db.query(Person).count() > 0:
            return

        demo = Person(
            app_name="OKC",
            name="Annie",
            location="NBO West",
            distance="4 km",
            age="23",
            phone="",
            status="New",
            tags="demo, friendly",
            notes="Demo profile only.",
            summary="Waiting for initial review.",
            red_flags="",
            green_flags="Good conversation flow.",
            boundaries="",
            reminders="Follow up this week.",
            reminder_date=datetime.utcnow().date(),
            initial_review_ready=False,
        )
        db.add(demo)
        db.flush()
        db.commit()


seed_demo_data()


def enrich_person(person: Person) -> None:
    person.uploads.sort(key=lambda item: item.created_at, reverse=True)
    person.upload_groups = upload_groups(person)
    general = person.upload_groups.get("general_photos", [])
    intake = person.upload_groups.get("profile_intake", [])
    person.primary_photo = None
    for item in general + intake:
        if item.content_type and item.content_type.startswith("image/"):
            person.primary_photo = item
            break


def build_profile_export(person: Person) -> str:
    lines = [
        f"Profile: {person.display_name}",
        f"Phone / WhatsApp: {person.phone or 'Not provided'}",
        f"Status: {person.status or 'New'}",
        f"Tags: {person.tags or 'None'}",
        f"Reminder Date: {person.reminder_date.isoformat() if person.reminder_date else 'Not set'}",
        "",
        "Summary",
        person.summary or "None",
        "",
        "Profile Parser Output",
        person.profile_parser_output or "None",
        "",
        "Bio Builder Source",
        "Use profile screenshots and copied text to build a clean profile bio.",
        "",
        "Private Notes",
        person.notes or "None",
        "",
        "Red Flags",
        person.red_flags or "None",
        "",
        "Green Flags",
        person.green_flags or "None",
        "",
        "Boundaries",
        person.boundaries or "None",
        "",
        "Follow-up Reminders",
        person.reminders or "None",
        "",
        "Conversation Thread",
        person.conversation_thread or "None",
        "",
        "Uploads",
    ]
    for item in person.uploads:
        lines.append(
            f"- [{item.created_at.strftime('%Y-%m-%d %H:%M')}] {(item.upload_category or 'profile_intake')} | {item.original_name} | {item.upload_note or 'no note'}"
        )
        if item.extracted_text:
            lines.append(f"  Extracted Text: {item.extracted_text}")
    return "\n".join(lines)


def build_profile_zip(person: Person) -> Path:
    export_folder = EXPORTS_ROOT / "profiles"
    export_folder.mkdir(parents=True, exist_ok=True)
    safe_label = f"{person.app_name}-{person.name}-{person.location}-{person.age or '??'}".replace(" ", "_").replace("/", "-")
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    zip_path = export_folder / f"{stamp}-{safe_label}.zip"
    text_name = f"{safe_label}.txt"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(text_name, build_profile_export(person))
        for item in person.uploads:
            source = UPLOADS_ROOT / item.stored_name
            if source.exists():
                archive.write(source, arcname=f"uploads/{item.original_name}")
    return zip_path


def build_profile_pdf(person: Person) -> Path:
    export_folder = EXPORTS_ROOT / "profiles"
    export_folder.mkdir(parents=True, exist_ok=True)
    safe_label = f"{person.app_name}-{person.name}-{person.location}-{person.age or '??'}".replace(" ", "_").replace("/", "-")
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    pdf_path = export_folder / f"{stamp}-{safe_label}.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter
    y = height - 40
    for line in build_profile_export(person).splitlines():
        if y < 40:
            pdf.showPage()
            y = height - 40
        pdf.drawString(40, y, line[:110])
        y -= 14
    pdf.save()
    return pdf_path


def merge_people(db: Session, source: Person, target: Person) -> None:
    source_tags = parse_tags(source.tags)
    target_tags = parse_tags(target.tags)
    target.tags = ", ".join(sorted(source_tags | target_tags))
    if not target.phone and source.phone:
        target.phone = source.phone
    if not target.notes and source.notes:
        target.notes = source.notes
    if not target.summary and source.summary:
        target.summary = source.summary
    if not target.red_flags and source.red_flags:
        target.red_flags = source.red_flags
    if not target.green_flags and source.green_flags:
        target.green_flags = source.green_flags
    if not target.boundaries and source.boundaries:
        target.boundaries = source.boundaries
    if not target.reminders and source.reminders:
        target.reminders = source.reminders
    if not target.reminder_date and source.reminder_date:
        target.reminder_date = source.reminder_date
    if not target.profile_parser_output and source.profile_parser_output:
        target.profile_parser_output = source.profile_parser_output
    if not target.conversation_thread and source.conversation_thread:
        target.conversation_thread = source.conversation_thread

    for item in source.uploads:
        item.person_id = target.id
    db.delete(source)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if is_logged_in(request):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error, "version": app_version()},
    )


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == os.getenv("ADMIN_USERNAME", "admin") and password == os.getenv("ADMIN_PASSWORD", "change-this-password"):
        response = RedirectResponse("/dashboard", status_code=302)
        response.set_cookie("session", os.getenv("SECRET_KEY", ""), httponly=True, samesite="lax")
        return response
    return RedirectResponse("/login?error=Invalid+login", status_code=302)


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    search: str = "",
    app_name: str = "",
    name: str = "",
    location: str = "",
    distance: str = "",
    age: str = "",
    status: str = "",
    tags: str = "",
):
    redirect = require_login(request)
    if redirect:
        return redirect

    filters = {
        "search": search,
        "app_name": app_name,
        "name": name,
        "location": location,
        "distance": distance,
        "age": age,
        "status": status,
        "tags": tags,
    }
    with get_db() as db:
        people = apply_person_filters(db, filters)
        tag_options = get_setting_options(db, "tag")
        for person in people:
            enrich_person(person)
            person.card_tags = sort_profile_tags(person, tag_options)[:3]
            person.extra_tag_count = max(0, len(parse_tags(person.tags)) - len(person.card_tags))
        duplicates = find_duplicates(people)
        reminder_groups = build_reminder_groups(people)
        calendar_month = build_calendar_month(people)
        totals = {
            "count": len(people),
            "profile_intake": sum(1 for person in people for upload in person.uploads if (upload.upload_category or "profile_intake") == "profile_intake"),
            "general_photos": sum(1 for person in people for upload in person.uploads if (upload.upload_category or "") == "general_photos"),
            "message_tracking": sum(1 for person in people for upload in person.uploads if (upload.upload_category or "") == "message_tracking"),
            "uploads": sum(len(person.uploads) for person in people),
        }
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "people": people,
            "filters": filters,
            "totals": totals,
            "duplicates": duplicates,
            "reminder_groups": reminder_groups,
            "calendar_month": calendar_month,
            "status_options": STATUS_OPTIONS,
            "version": app_version(),
        },
    )


@app.post("/profiles/export-csv")
def export_profiles_csv(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        people = db.query(Person).order_by(Person.created_at.desc()).all()
        csv_text = build_profiles_csv(people)
    filename = f"social-keeper-profiles-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/settings/backup")
def download_full_backup(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    backup_path = build_full_backup()
    return FileResponse(backup_path, filename=backup_path.name, media_type="application/zip")


@app.get("/manage", response_class=HTMLResponse)
def manage_page(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        people = db.query(Person).order_by(Person.created_at.desc()).all()
        status_options = get_setting_values(db, "status", STATUS_OPTIONS)
    return templates.TemplateResponse(
        request=request,
        name="manage.html",
        context={"people": people, "status_options": status_options, "version": app_version()},
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        tags = get_setting_options(db, "tag")
        statuses = get_setting_options(db, "status")
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"tags": tags, "statuses": statuses, "version": app_version()},
    )


@app.post("/settings/options")
def add_setting_option(
    request: Request,
    kind: str = Form(...),
    value: str = Form(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    clean_kind = kind.strip()
    clean_value = value.strip()
    if clean_kind not in {"tag", "status"} or not clean_value:
        return RedirectResponse("/settings", status_code=302)

    with get_db() as db:
        exists = db.query(SettingOption).filter(SettingOption.kind == clean_kind, SettingOption.value.ilike(clean_value)).first()
        if not exists:
            db.add(SettingOption(kind=clean_kind, value=clean_value, sort_order=next_sort_order(db, clean_kind)))
            db.commit()
    return RedirectResponse("/settings", status_code=302)


@app.post("/settings/options/{option_id}/delete")
def delete_setting_option(request: Request, option_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        option = db.get(SettingOption, option_id)
        if option:
            db.delete(option)
            db.commit()
    return RedirectResponse("/settings", status_code=302)


@app.post("/settings/options/{option_id}/edit")
def edit_setting_option(
    request: Request,
    option_id: int,
    value: str = Form(...),
    sort_order: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    clean_value = value.strip()
    if not clean_value:
        return RedirectResponse("/settings", status_code=302)

    with get_db() as db:
        option = db.get(SettingOption, option_id)
        if option:
            option.value = clean_value
            option.sort_order = int(sort_order) if sort_order.strip().isdigit() else option.sort_order
            db.commit()
    return RedirectResponse("/settings", status_code=302)


@app.post("/profiles/bulk-update")
def bulk_update_profiles(
    request: Request,
    profile_ids: list[int] = Form([]),
    bulk_status: str = Form(""),
    bulk_add_tag: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        for person_id in profile_ids:
            person = db.get(Person, person_id)
            if not person:
                continue
            if bulk_status.strip():
                person.status = bulk_status.strip()
            if bulk_add_tag.strip():
                tags = parse_tags(person.tags)
                tags.add(bulk_add_tag.strip())
                person.tags = ", ".join(sorted(tags))
        db.commit()
    return RedirectResponse("/manage", status_code=302)


@app.post("/profiles/merge")
def merge_profiles(
    request: Request,
    source_id: int = Form(...),
    target_id: int = Form(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect
    if source_id == target_id:
        return RedirectResponse("/dashboard", status_code=302)

    with get_db() as db:
        source = db.get(Person, source_id)
        target = db.get(Person, target_id)
        if source and target:
            merge_people(db, source, target)
            db.commit()
            return RedirectResponse(f"/profiles/{target.id}", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@app.post("/uploads/{upload_id}/metadata")
def update_upload_metadata(
    request: Request,
    upload_id: int,
    upload_note: str = Form(""),
    extracted_text: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        upload = db.get(UploadItem, upload_id)
        if not upload:
            return RedirectResponse("/dashboard", status_code=302)
        upload.upload_note = upload_note.strip()
        upload.extracted_text = extracted_text.strip()
        person_id = upload.person_id
        db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.get("/profiles/new", response_class=HTMLResponse)
def new_profile(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    with get_db() as db:
        status_options = get_setting_values(db, "status", STATUS_OPTIONS)
        tag_options = get_setting_values(db, "tag", [])
    return templates.TemplateResponse(
        request=request,
        name="new_profile.html",
        context={"version": app_version(), "status_options": status_options, "tag_options": tag_options},
    )


@app.post("/profiles")
def create_profile(
    request: Request,
    app_name: str = Form(...),
    name: str = Form(...),
    location: str = Form(...),
    distance: str = Form(""),
    age: str = Form("??"),
    phone: str = Form(""),
    status: str = Form("New"),
    selected_tags: list[str] = Form([]),
    notes: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    clean_age = age.strip() or "??"
    with get_db() as db:
        person = Person(
            app_name=app_name.strip(),
            name=name.strip(),
            location=location.strip(),
            distance=distance.strip(),
            age=clean_age,
            phone=phone.strip(),
            status=status.strip() or "New",
            tags=", ".join(sorted({tag.strip() for tag in selected_tags if tag.strip()})),
            notes=notes.strip(),
        )
        db.add(person)
        db.commit()
        db.refresh(person)
    return RedirectResponse(f"/profiles/{person.id}", status_code=302)


@app.post("/profiles/{person_id}/edit")
def update_profile(
    request: Request,
    person_id: int,
    app_name: str = Form(...),
    name: str = Form(...),
    location: str = Form(...),
    distance: str = Form(""),
    age: str = Form("??"),
    phone: str = Form(""),
    status: str = Form("New"),
    selected_tags: list[str] = Form([]),
    new_tag: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person:
            person.app_name = app_name.strip()
            person.name = name.strip()
            person.location = location.strip()
            person.distance = distance.strip()
            person.age = age.strip() or "??"
            person.phone = phone.strip()
            person.status = status.strip() or "New"
            tags = {tag.strip() for tag in selected_tags if tag.strip()}
            if new_tag.strip():
                tags.add(new_tag.strip())
                exists = db.query(SettingOption).filter(SettingOption.kind == "tag", SettingOption.value.ilike(new_tag.strip())).first()
                if not exists:
                    db.add(SettingOption(kind="tag", value=new_tag.strip(), sort_order=next_sort_order(db, "tag")))
            person.tags = ", ".join(sorted(tags))
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.get("/profiles/{person_id}", response_class=HTMLResponse)
def profile_detail(request: Request, person_id: int, conversation_search: str = ""):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if not person:
            return RedirectResponse("/dashboard", status_code=302)
        enrich_person(person)
        status_options = get_setting_values(db, "status", STATUS_OPTIONS)
        tag_options = get_setting_values(db, "tag", [])
        return templates.TemplateResponse(
            request=request,
            name="profile_detail.html",
            context={
                "person": person,
                "conversation_search": conversation_search,
                "conversation_results": [
                    line
                    for line in (person.conversation_thread or "").splitlines()
                    if conversation_search.strip() and conversation_search.strip().lower() in line.lower()
                ] if conversation_search.strip() else [],
                "version": app_version(),
                "status_options": status_options,
                "tag_options": tag_options,
                "upload_categories": UPLOAD_CATEGORIES,
            },
        )


@app.post("/profiles/{person_id}/notes")
def update_notes(
    request: Request,
    person_id: int,
    notes: str = Form(""),
    summary: str = Form(""),
    red_flags: str = Form(""),
    green_flags: str = Form(""),
    boundaries: str = Form(""),
    reminders: str = Form(""),
    reminder_date: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person:
            person.notes = notes
            person.summary = summary
            person.red_flags = red_flags
            person.green_flags = green_flags
            person.boundaries = boundaries
            person.reminders = reminders
            person.reminder_date = datetime.strptime(reminder_date, "%Y-%m-%d").date() if reminder_date else None
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/uploads")
async def upload_file(
    request: Request,
    person_id: int,
    uploaded_file: UploadFile = File(...),
    upload_category: str = Form("profile_intake"),
    upload_note: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person and uploaded_file.filename:
            chosen_category = upload_category if upload_category in UPLOAD_CATEGORIES else "profile_intake"
            person_folder = UPLOADS_ROOT / str(person_id)
            person_folder.mkdir(parents=True, exist_ok=True)
            safe_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}-{uploaded_file.filename}"
            target = person_folder / safe_name
            with target.open("wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            extracted_text = ""
            if target.suffix.lower() == ".txt":
                extracted_text = read_text_file(target)
            db.add(
                UploadItem(
                    person_id=person_id,
                    original_name=uploaded_file.filename,
                    stored_name=f"{person_id}/{safe_name}",
                    content_type=uploaded_file.content_type,
                    upload_category=chosen_category,
                    upload_note=upload_note.strip(),
                    extracted_text=extracted_text,
                )
            )
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/build-bio")
def build_profile_bio(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person:
            summary_text, parser_output = build_profile_intake_parser(person)
            person.profile_parser_output = parser_output
            if summary_text:
                person.summary = summary_text
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/build-conversation")
def build_conversation_thread(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person:
            person.conversation_thread = build_conversation_parser(person)
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/export")
def export_profile(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if not person:
            return RedirectResponse("/dashboard", status_code=302)
        enrich_person(person)
        export_folder = EXPORTS_ROOT / "profiles"
        export_folder.mkdir(parents=True, exist_ok=True)
        safe_label = f"{person.app_name}-{person.name}-{person.location}-{person.age or '??'}".replace(" ", "_").replace("/", "-")
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{safe_label}.txt"
        target = export_folder / filename
        target.write_text(build_profile_export(person), encoding="utf-8")
    return FileResponse(target, filename=filename, media_type="text/plain")


@app.post("/profiles/{person_id}/export-zip")
def export_profile_zip(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if not person:
            return RedirectResponse("/dashboard", status_code=302)
        enrich_person(person)
        zip_path = build_profile_zip(person)
    return FileResponse(zip_path, filename=zip_path.name, media_type="application/zip")


@app.post("/profiles/{person_id}/export-pdf")
def export_profile_pdf(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if not person:
            return RedirectResponse("/dashboard", status_code=302)
        enrich_person(person)
        pdf_path = build_profile_pdf(person)
    return FileResponse(pdf_path, filename=pdf_path.name, media_type="application/pdf")


@app.get("/uploads/{upload_path:path}")
def open_upload(upload_path: str):
    return FileResponse(UPLOADS_ROOT / upload_path)
