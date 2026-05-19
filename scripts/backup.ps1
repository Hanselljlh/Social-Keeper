param(
    [string]$OutputDir = ".\data\exports\backups"
)

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupName = "social-keeper-backup-$timestamp.zip"
$backupPath = Join-Path $OutputDir $backupName

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Compress-Archive -Path ".\data\database", ".\data\uploads", ".\data\exports", ".\data\config", ".\data\logs" -DestinationPath $backupPath -Force

Write-Output "Backup created: $backupPath"
