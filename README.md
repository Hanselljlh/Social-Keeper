# Social Keeper

Private self-hosted web app for organizing social and dating contact information with structured upload lanes.

## What this first version includes
- Login page
- Browse-first dashboard with profile cards
- Create profile form
- Profile detail page
- Separate manage screen for bulk updates
- Settings screen for reusable tags and status choices
- Settings edit-in-place for tags and status choices
- Structured upload lanes
- Profile bio and notes area
- Profile export
- Bulk status/tag updates
- Duplicate profile checking
- Reminder calendar view
- ZIP export bundles
- Real reminder dates
- Duplicate merge action
- PDF export
- Profile intake bio builder
- Searchable conversation thread builder
- Automatic `.txt` message import
- Docker Compose setup
- External data folders

## Main workflow
- Browse profiles from the dashboard using a card view with photo, name, age, location, distance, status, and tags
- Open a profile to manage basic info, uploads, and notes
- Use `Manage` for bulk status/tag updates
- Use `Settings` to add, edit, or remove reusable tags and status choices
- Use `Build Bio From Intake Files` to turn profile screenshots/copied text into a draft profile bio
- Use `Build Conversation Thread` to combine message tracking files into one readable thread
- Use conversation search on each profile to find text inside the generated thread

## Before you start
1. Copy `.env.example` to `.env`
2. Change `SECRET_KEY`
3. Change `ADMIN_PASSWORD`

## Folder safety
Your real data is stored outside the app code inside `./data/`

- `./data/database` = database
- `./data/uploads` = uploaded files
- `./data/exports` = generated exports
- `./data/config` = config
- `./data/logs` = logs

You can update the app code with `git pull` without putting your real data inside the repo code.

## First setup
```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open:

`http://localhost:8000`

Login with the values from `.env`

## Start later
```powershell
docker compose up -d
```

## Stop
```powershell
docker compose down
```

## Update
```powershell
git pull
docker compose up -d --build
```

## Backup
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
```

Backup files are saved in:

`./data/exports/backups`

## Restore
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -BackupFile .\data\exports\backups\YOUR_BACKUP.zip
```

## Demo data
This project includes fake demo records only.
Do not place real data inside the repo itself.

## Notes
- Local only by default
- No third-party analytics
- No external API use unless you add that later
- Profiles include a `distance` field in the basic info
- Upload lanes are split into profile intake, general photos, and message tracking
- Uploaded `.txt` files are read automatically into message tracking text
- Screenshot-based automation still depends on copied text or manually filled extracted text fields
