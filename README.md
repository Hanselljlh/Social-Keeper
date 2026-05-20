# Social Keeper

Private self-hosted web app for organizing social and dating conversation information.

## What this first version includes
- Login page
- Dashboard
- Create profile form
- Profile detail page
- Upload area
- Notes area
- Timeline area
- Timeline editing
- Profile export
- Bulk status/tag updates
- Duplicate profile checking
- Reminder calendar view
- ZIP export bundles
- Real reminder dates
- Duplicate merge action
- PDF export
- Docker Compose setup
- External data folders

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
