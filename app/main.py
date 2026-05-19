from pathlib import Path
import os
import secrets
import shutil
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
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
    initial_review_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    timeline_items: Mapped[list["TimelineItem"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    uploads: Mapped[list["UploadItem"]] = relationship(back_populates="person", cascade="all, delete-orphan")

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    person: Mapped[Person] = relationship(back_populates="uploads")


engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base.metadata.create_all(engine)

app = FastAPI(title=os.getenv("APP_NAME", "Social Keeper"))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=UPLOADS_ROOT), name="media")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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
            initial_review_ready=False,
        )
        db.add(demo)
        db.flush()
        db.add(TimelineItem(person_id=demo.id, item_type="message", content="Demo timeline item."))
        db.commit()


seed_demo_data()


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
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        people = db.query(Person).order_by(Person.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"people": people, "version": app_version()},
    )


@app.get("/profiles/new", response_class=HTMLResponse)
def new_profile(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request=request,
        name="new_profile.html",
        context={"version": app_version()},
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
            status=status.strip(),
            tags=tags.strip(),
            notes=notes.strip(),
        )
        db.add(person)
        db.commit()
        db.refresh(person)
    return RedirectResponse(f"/profiles/{person.id}", status_code=302)


@app.get("/profiles/{person_id}", response_class=HTMLResponse)
def profile_detail(request: Request, person_id: int):
    redirect = require_login(request)
    if redirect:
        return redirect

    with get_db() as db:
        person = db.get(Person, person_id)
        if not person:
            return RedirectResponse("/dashboard", status_code=302)
        person.timeline_items.sort(key=lambda item: item.created_at, reverse=True)
        person.uploads.sort(key=lambda item: item.created_at, reverse=True)
        return templates.TemplateResponse(
            request=request,
            name="profile_detail.html",
            context={"person": person, "version": app_version()},
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
            person.initial_review_ready = initial_review_ready == "true"
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


@app.post("/profiles/{person_id}/uploads")
async def upload_file(request: Request, person_id: int, uploaded_file: UploadFile = File(...)):
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
                )
            )
            db.commit()
    return RedirectResponse(f"/profiles/{person_id}", status_code=302)


@app.get("/uploads/{upload_path:path}")
def open_upload(upload_path: str):
    return FileResponse(UPLOADS_ROOT / upload_path)
