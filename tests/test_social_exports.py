from datetime import date
import zipfile

from app.main import Person, build_calendar_month, build_profiles_csv, build_full_backup


def make_person(name, reminder_date=None, tags="follow-up"):
    return Person(
        app_name="OKC",
        name=name,
        location="NBO West",
        distance="4 km",
        age="23",
        phone="555-0100",
        status="Talking",
        tags=tags,
        notes="Private note",
        summary="Profile summary",
        red_flags="",
        green_flags="Good conversation",
        boundaries="Go slow",
        reminders="Follow up",
        reminder_date=reminder_date,
    )


def test_profiles_csv_contains_core_social_fields_and_reminder_dates():
    people = [make_person("Annie", date(2026, 6, 12))]

    csv_text = build_profiles_csv(people)

    assert "app_name,name,location,distance,age,phone,status,tags,reminder_date,summary,notes" in csv_text
    assert "OKC,Annie,NBO West,4 km,23,555-0100,Talking,follow-up,2026-06-12" in csv_text


def test_calendar_month_groups_profiles_by_day_and_keeps_blanks():
    people = [make_person("Annie", date(2026, 5, 12)), make_person("Beth", date(2026, 5, 12))]

    month = build_calendar_month(people, 2026, 5)

    assert month["label"] == "May 2026"
    assert len(month["weeks"]) >= 5
    day_12 = next(day for week in month["weeks"] for day in week if day["date"] == date(2026, 5, 12))
    assert [person.name for person in day_12["people"]] == ["Annie", "Beth"]
    assert any(day["date"] is None for day in month["weeks"][0])


def test_full_backup_zip_contains_database_uploads_and_exports(tmp_path):
    db_path = tmp_path / "database" / "social_keeper.db"
    uploads_root = tmp_path / "uploads"
    exports_root = tmp_path / "exports"
    db_path.parent.mkdir()
    uploads_root.mkdir()
    exports_root.mkdir()
    db_path.write_text("db", encoding="utf-8")
    (uploads_root / "photo.txt").write_text("photo", encoding="utf-8")
    (exports_root / "old.txt").write_text("export", encoding="utf-8")

    backup_path = build_full_backup(db_path, uploads_root, exports_root, tmp_path / "backups")

    assert backup_path.exists()
    with zipfile.ZipFile(backup_path) as archive:
        names = set(archive.namelist())
    assert "database/social_keeper.db" in names
    assert "uploads/photo.txt" in names
    assert "exports/old.txt" in names
