from pathlib import Path
import os
import secrets
import shutil
import zipfile
from datetime import date, datetime
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
    reminder_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    initial_review_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    timeline_items: Mapped[list["TimelineItem"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    uploads: Mapped[list["UploadItem"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    message_items: Mapped[list["MessageItem"]] = relationship(back_populates="person", cascade="all, delete-orphan")

    @property
    def display_name(self) -> str:
        age_value = self.age if self.age else "??"
        return f"{self.app_name} - {self.name} - {self.location} - {age_value}"


class TimelineItem(Base):
    __tablename__ = "timeline_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    item_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Person] = relationship(back_populates="timeline_items")


class UploadItem(Base):
    __tablename__ = "upload_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    upload_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Person] = relationship(back_populates="uploads")


class MessageItem(Base):
    __tablename__ = "message_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"))
    bucket: Mapped[str] = mapped_column(String(20))
    tone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Person] = relationship(back_populates="message_items")


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
ensure_column("upload_items", "upload_note", "TEXT")
ensure_column("people", "reminder_date", "DATE")

app = FastAPI(title=os.getenv("APP_NAME", "Social Keeper"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=UPLOADS_ROOT), name="media")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

INITIAL_OPTIONS = [
    (
        "general nice to meet",
        "Hey {name}, nice meeting you on {app_name}. You seem easy to talk to. How is your day going?",
    ),
    (
        "more flirty",
        "Hey {name}, you definitely caught my attention on {app_name}. I had to say hi properly.",
    ),
]

FOLLOW_UP_OPTIONS = [
    (
        "general flirty conversation",
        "You seem fun to talk to. What kind of trouble do you usually get into when you are in a good mood?",
    ),
    (
        "more direct flirty, edgy",
        "You have that look like you know exactly how to behave and still choose not to. I like that.",
    ),
    (
        "more sexually flirty with physical compliments and sexually underpinned suggestions",
        "You have a very tempting look in your pictures. I can already tell being around you would be distracting in the best way.",
    ),
]

STATUS_OPTIONS = ["New", "Talking", "Follow Up", "Date Planned", "Met", "Paused", "Closed"]
TIMELINE_OPTIONS = ["message", "event", "date", "logistics", "payment", "upload received"]


def app_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


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


def parse_tags(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    return {part.strip() for part in value.split(",") if part.strip()}


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

    for field in ["app_name", "name", "location", "age", "status", "tags"]:
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


def seed_demo_data() -> None:
    with SessionLocal() as db:
        if db.query(Person).count() > 0:
            return

        demo = Person(
            app_name="OKC",
            name="Annie",
            location="NBO West",
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
        db.add(TimelineItem(person_id=demo.id, item_type="message", content="Demo timeline item."))
        db.add(
            MessageItem(
                person_id=demo.id,
                bucket="draft",
                tone="general nice to meet",
                content="Hey Annie, nice meeting you on OKC. You seem easy to talk to.",
            )
        )
        db.commit()


seed_demo_data()


def enrich_person(person: Person) -> None:
    person.timeline_items.sort(key=lambda item: item.created_at, reverse=True)
    person.uploads.sort(key=lambda item: item.created_at, reverse=True)
    person.message_items.sort(key=lambda item: item.created_at, reverse=True)
    person.initial_message_items = [item for item in person.message_items if item.bucket == "initial"]
    person.followup_message_items = [item for item in person.message_items if item.bucket == "follow_up"]
    person.saved_drafts = [item for item in person.message_items if item.bucket == "draft"]
    person.sent_history = [item for item in person.message_items if item.bucket == "sent"]
    person.review_overview_display = person.review_overview if person.initial_review_ready else ""


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
        "Structured Overview",
        person.review_overview or "Not ready",
        "",
        "Timeline",
    ]
    for item in person.timeline_items:
        lines.append(f"- [{item.created_at.strftime('%Y-%m-%d %H:%M')}] {item.item_type}: {item.content}")
    lines.extend(["", "Messages"])
    for item in person.message_items:
        lines.append(f"- [{item.created_at.strftime('%Y-%m-%d %H:%M')}] {item.bucket} / {item.tone or 'no label'}: {item.content}")
    lines.extend(["", "Uploads"])
    for item in person.uploads:
        lines.append(f"- [{item.created_at.strftime('%Y-%m-%d %H:%M')}] {item.original_name} | {item.upload_note or 'no note'}")
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
    if source.initial_review_ready and not target.initial_review_ready:
        target.initial_review_ready = True
        target.review_overview = source.review_overview

    for item in source.timeline_items:
        item.person_id = target.id
    for item in source.uploads:
        item.person_id = target.id
    for item in source.message_items:
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
        "age": age,
        "status": status,
        "tags": tags,
    }
    with get_db() as db:
        people = apply_person_filters(db, filters)
        duplicates = find_duplicates(people)
        reminder_groups = build_reminder_groups(people)
        totals = {
            "count": len(people),
            "ready": sum(1 for person in people if person.initial_review_ready),
            "needs_review": sum(1 for person in people if not person.initial_review_ready),
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
            "status_options": STATUS_OPTIONS,
            "version": app_version(),
        },
    )


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
    return RedirectResponse("/dashboard", status_code=302)


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


@app.get("/profiles/new", response_class=HTMLResponse)
def new_profile(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="new_profile.html",
        context={"version": app_version(), "status_options": STATUS_OPTIONS},
    )


@app.post("/profiles")
def create_profile(
    request: Request,
    app_name: str = Form(...),
    name: str = Form(...),
    location: str = Form(...),
    age: str = Form("??"),
    phone: str = Form(""),
    status: str = Form("New"),
    tags: str = Form(""),
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
            age=clean_age,
            phone=phone.strip(),
            status=status.strip() or "New",
            tags=tags.strip(),
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
    age: str = Form("??"),
    phone: str = Form(""),
    status: str = Form("New"),
    tags: str = Form(""),
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
            person.age = age.strip() or "??"
            person.phone = phone.strip()
            person.status = status.strip() or "New"
            person.tags = tags.strip()
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.get("/profiles/{person_id}", response_class=HTMLResponse)
def profile_detail(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if not person:
            return RedirectResponse("/dashboard", status_code=302)
        enrich_person(person)
        initial_options = [(tone, content.format(name=person.name, app_name=person.app_name)) for tone, content in INITIAL_OPTIONS]
        follow_up_options = [(tone, content.format(name=person.name, app_name=person.app_name)) for tone, content in FOLLOW_UP_OPTIONS]
        return templates.TemplateResponse(
            request=request,
            name="profile_detail.html",
            context={
                "person": person,
                "version": app_version(),
                "status_options": STATUS_OPTIONS,
                "timeline_options": TIMELINE_OPTIONS,
                "initial_options": initial_options,
                "follow_up_options": follow_up_options,
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
    initial_review_ready: str = Form("false"),
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
            person.initial_review_ready = initial_review_ready == "true"
            person.review_overview = build_review_overview(person) if person.initial_review_ready else ""
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/timeline")
def add_timeline_item(
    request: Request,
    person_id: int,
    item_type: str = Form(...),
    content: str = Form(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person and content.strip():
            db.add(TimelineItem(person_id=person_id, item_type=item_type.strip(), content=content.strip()))
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/timeline/{timeline_id}/edit")
def edit_timeline_item(
    request: Request,
    person_id: int,
    timeline_id: int,
    item_type: str = Form(...),
    content: str = Form(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        item = db.get(TimelineItem, timeline_id)
        if item and item.person_id == person_id:
            item.item_type = item_type.strip()
            item.content = content.strip()
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/timeline/{timeline_id}/delete")
def delete_timeline_item(request: Request, person_id: int, timeline_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        item = db.get(TimelineItem, timeline_id)
        if item and item.person_id == person_id:
            db.delete(item)
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/messages")
def add_message_item(
    request: Request,
    person_id: int,
    bucket: str = Form(...),
    tone: str = Form(""),
    content: str = Form(...),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    if bucket not in {"initial", "follow_up", "draft", "sent"}:
        return RedirectResponse(f"/profiles/{person_id}", status_code=302)

    with get_db() as db:
        person = db.get(Person, person_id)
        if person and content.strip():
            db.add(MessageItem(person_id=person_id, bucket=bucket, tone=tone.strip(), content=content.strip()))
            if bucket == "sent":
                db.add(TimelineItem(person_id=person_id, item_type="message", content=f"Sent message: {content.strip()}"))
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.post("/profiles/{person_id}/uploads")
async def upload_file(
    request: Request,
    person_id: int,
    uploaded_file: UploadFile = File(...),
    upload_note: str = Form(""),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if person and uploaded_file.filename:
            person_folder = UPLOADS_ROOT / str(person_id)
            person_folder.mkdir(parents=True, exist_ok=True)
            safe_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}-{uploaded_file.filename}"
            target = person_folder / safe_name
            with target.open("wb") as buffer:
                shutil.copyfileobj(uploaded_file.file, buffer)
            db.add(
                UploadItem(
                    person_id=person_id,
                    original_name=uploaded_file.filename,
                    stored_name=f"{person_id}/{safe_name}",
                    content_type=uploaded_file.content_type,
                    upload_note=upload_note.strip(),
                )
            )
            db.add(
                TimelineItem(
                    person_id=person_id,
                    item_type="upload received",
                    content=f"Upload received: {uploaded_file.filename}",
                )
            )
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
