param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Server = "harrisserver"
$ProjectDir = $PSScriptRoot

$ArchiveName = "training-etl-deploy.tar.gz"
$LocalArchive = Join-Path $env:TEMP $ArchiveName
$RemoteArchive = "/tmp/$ArchiveName"
$RemoteStage = "/tmp/training-etl-deploy"

try {
    if (-not (Test-Path (Join-Path $ProjectDir "src"))) {
        throw "Run this script from the training-etl repository root."
    }

    foreach ($RequiredFile in @(
            "Dockerfile",
            "requirements.txt",
            "docker-compose.server.yml"
        )) {
        if (-not (Test-Path (Join-Path $ProjectDir $RequiredFile))) {
            throw "Required file not found: $RequiredFile"
        }
    }

    Write-Host ""
    Write-Host "Packaging training-etl..." -ForegroundColor Cyan
    Write-Host "Uncommitted changes are included." -ForegroundColor Yellow

    if (Test-Path $LocalArchive) {
        Remove-Item $LocalArchive -Force
    }

    Push-Location $ProjectDir

    try {
        tar.exe -czf $LocalArchive `
            --exclude="__pycache__" `
            --exclude="*.pyc" `
            --exclude=".DS_Store" `
            src `
            Dockerfile `
            requirements.txt `
            docker-compose.server.yml

        if ($LASTEXITCODE -ne 0) {
            throw "Archive creation failed."
        }
    }
    finally {
        Pop-Location
    }

    if ($DryRun) {
        Write-Host ""
        Write-Host "Dry run complete. Archive contents:" -ForegroundColor Green
        tar.exe -tzf $LocalArchive

        Write-Host ""
        Write-Host "No files were uploaded or changed."
        exit 0
    }

    Write-Host "Uploading archive..."

    scp.exe -o BatchMode=yes `
        $LocalArchive `
        "${Server}:${RemoteArchive}"

    if ($LASTEXITCODE -ne 0) {
        throw "Archive upload failed."
    }

    Write-Host "Extracting files on harrisserver..."

    $RemoteCommand = "set -e; rm -rf '$RemoteStage'; mkdir -p '$RemoteStage'; tar -xzf '$RemoteArchive' -C '$RemoteStage'; cp -a '$RemoteStage/src/.' '/opt/training/etl/'; cp '$RemoteStage/Dockerfile' '$RemoteStage/requirements.txt' '/opt/training/etl-build/'; cp '$RemoteStage/docker-compose.server.yml' '/opt/training/docker-compose.server.yml'; sed -i 's/\r`$//' '/opt/training/etl/check_system_health.py' '/opt/training/etl/backup_postgres.sh' '/opt/training/etl/backup_test_latest_postgres.sh'; chmod 755 '/opt/training/etl/check_system_health.py' '/opt/training/etl/backup_postgres.sh' '/opt/training/etl/backup_test_latest_postgres.sh'; rm -rf '$RemoteStage'; rm -f '$RemoteArchive'; echo 'Deployment complete.'"

    $SshArguments = @(
        "-o"
        "BatchMode=yes"
        $Server
        $RemoteCommand
    )

    & ssh.exe @SshArguments

    if ($LASTEXITCODE -ne 0) {
        throw "Server deployment failed."
    }

    Write-Host ""
    Write-Host "Training-etl deployed successfully." -ForegroundColor Green
    Write-Host "Containers were not rebuilt or restarted."
}
catch {
    Write-Host ""
    Write-Host "Deployment failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if (Test-Path $LocalArchive) {
        Remove-Item $LocalArchive -Force
    }
}