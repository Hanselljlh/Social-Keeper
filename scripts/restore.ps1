param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

if (-Not (Test-Path $BackupFile)) {
    Write-Error "Backup file not found: $BackupFile"
    exit 1
}

New-Item -ItemType Directory -Force -Path ".\data" | Out-Null
Expand-Archive -Path $BackupFile -DestinationPath ".\data\restore-temp" -Force

foreach ($folder in @("database", "uploads", "exports", "config", "logs")) {
    $source = Join-Path ".\data\restore-temp\data" $folder
    $target = Join-Path ".\data" $folder
    if (Test-Path $source) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Remove-Item -LiteralPath ".\data\restore-temp" -Recurse -Force
Write-Output "Restore finished."
