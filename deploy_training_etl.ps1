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
$WeeklyHealthReportPath = "/opt/training/etl/weekly_health_report.py"
$OperationalEntrypoints = @(
    "/opt/training/etl/check_system_health.py",
    "/opt/training/etl/backup_postgres.sh",
    "/opt/training/etl/backup_test_latest_postgres.sh",
    $WeeklyHealthReportPath
)
$RemoteEntrypointPaths = ($OperationalEntrypoints | ForEach-Object { "'$_'" }) -join " "

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

    Push-Location $ProjectDir
    try {
        $workingTree = @(git.exe status --porcelain)
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect Git working tree."
        }
        if ($workingTree.Count -gt 0) {
            throw "Deployment requires a clean Git working tree."
        }
        $revision = (git.exe rev-parse HEAD).Trim()
        $upstreamRevision = (git.exe rev-parse --verify '@{u}').Trim()
        if ($LASTEXITCODE -ne 0 -or $revision -notmatch '^[0-9a-f]{40}$' -or $revision -ne $upstreamRevision) {
            throw "Deployment requires HEAD to equal its configured upstream revision."
        }
        Write-Host "Deploying revision $revision" -ForegroundColor DarkCyan
    }
    finally {
        Pop-Location
    }

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

    $RemoteCommandTemplate = @'
set -e
rm -rf '__REMOTE_STAGE__'
mkdir -p '__REMOTE_STAGE__'
tar -xzf '__REMOTE_ARCHIVE__' -C '__REMOTE_STAGE__'
cp -a '__REMOTE_STAGE__/src/.' '/opt/training/etl/'
cp '__REMOTE_STAGE__/Dockerfile' '__REMOTE_STAGE__/requirements.txt' '/opt/training/etl-build/'
cp '__REMOTE_STAGE__/docker-compose.server.yml' '/opt/training/docker-compose.server.yml'
sed -i 's/\r$//' __REMOTE_ENTRYPOINTS__
chmod 755 __REMOTE_ENTRYPOINTS__
if ! test -f '__WEEKLY_REPORT__'; then
    echo 'Deployment assertion failed: weekly_health_report.py is not a regular file.' >&2
    exit 1
fi
if ! test -x '__WEEKLY_REPORT__'; then
    echo 'Deployment assertion failed: weekly_health_report.py is not executable.' >&2
    exit 1
fi
if [ "$(head -n 1 '__WEEKLY_REPORT__')" != '#!/usr/bin/env python3' ]; then
    echo 'Deployment assertion failed: weekly_health_report.py has an invalid shebang or CRLF line ending.' >&2
    exit 1
fi
rm -rf '__REMOTE_STAGE__'
rm -f '__REMOTE_ARCHIVE__'
echo 'Deployment complete.'
'@
    $RemoteCommand = $RemoteCommandTemplate.Replace("__REMOTE_STAGE__", $RemoteStage)
    $RemoteCommand = $RemoteCommand.Replace("__REMOTE_ARCHIVE__", $RemoteArchive)
    $RemoteCommand = $RemoteCommand.Replace("__REMOTE_ENTRYPOINTS__", $RemoteEntrypointPaths)
    $RemoteCommand = $RemoteCommand.Replace("__WEEKLY_REPORT__", $WeeklyHealthReportPath)
    $RemoteCommand = $RemoteCommand.Replace("`r`n", "`n")

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
    Write-Host "No containers were rebuilt or restarted by this script."
    Write-Host "Apply the documented restart, recreation, or rebuild action for the changed artifact."
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