<#
Weekly restore drill for the member onboarding database, on the DB server.

pg_backup.ps1 (erp_master) dumps every database nightly as postgres. This proves the
newest member_onboarding dump really restores: it restores into a scratch database,
counts each organization's forms, members, documents and staff, and drops it again.
A failure is written to the log and ends the task with exit code 1.

Schedule it weekly, after the nightly backup:
  $action  = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -ExecutionPolicy Bypass -File "E:\MySQLBackups\restore_check.ps1"'
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 4:00AM
  Register-ScheduledTask -TaskName "Onboarding Restore Check" -Action $action -Trigger $trigger -User "SYSTEM" -RunLevel Highest
#>

# ---------------- settings ----------------
$PgBin      = "E:\postgres\16\bin"
$PgHost     = "127.0.0.1"
$PgPort     = 5432
$PgUser     = "postgres"
$PgPassFile = "E:\MySQLBackups\pgpass.conf"
$DumpDir    = "E:\MySQLBackups\DBBACKUP"
$Database   = "member_onboarding"
$Scratch    = "member_onboarding_restore_check"
# The newest dump must be younger than this, or the nightly backup has stopped.
$MaxAgeHours = 30
# ------------------------------------------

$ErrorActionPreference = "Stop"
$env:PGPASSFILE = $PgPassFile
$logFile = Join-Path $DumpDir "restore_check.log"
$conn = @("-h", $PgHost, "-p", $PgPort, "-U", $PgUser, "-w")
$psql = Join-Path $PgBin "psql.exe"

function Log($text) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $text"
    Write-Output $line
    Add-Content -Path $logFile -Value $line
}

function Drop-Scratch {
    & $psql @conn -d postgres -q -c "DROP DATABASE IF EXISTS $Scratch WITH (FORCE)" | Out-Null
}

$failed = $false
try {
    $dump = Get-ChildItem $DumpDir -Filter "${Database}_*.dump" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $dump) { throw "no ${Database}_*.dump in ${DumpDir}: is $Database being backed up?" }
    $age = [int]((Get-Date) - $dump.LastWriteTime).TotalHours
    Log "checking $($dump.Name) ($([math]::Round($dump.Length / 1MB, 1)) MB, $age hours old)"
    if ($age -gt $MaxAgeHours) { throw "the newest dump is $age hours old: the nightly backup has stopped" }

    Drop-Scratch
    & (Join-Path $PgBin "createdb.exe") @conn $Scratch
    if ($LASTEXITCODE -ne 0) { throw "createdb exit $LASTEXITCODE" }
    & (Join-Path $PgBin "pg_restore.exe") @conn -d $Scratch --no-owner --no-acl --exit-on-error $dump.FullName
    if ($LASTEXITCODE -ne 0) { throw "pg_restore exit $LASTEXITCODE" }

    # postgres is a superuser, so row-level security does not hide rows from these counts.
    $query = @"
SELECT o.slug,
  (SELECT count(*) FROM application a WHERE a.organization_id = o.id),
  (SELECT count(*) FROM member m WHERE m.organization_id = o.id),
  (SELECT count(*) FROM application_document d WHERE d.organization_id = o.id),
  (SELECT count(*) FROM organization_membership s WHERE s.organization_id = o.id)
FROM organization o ORDER BY o.slug
"@
    $rows = & $psql @conn -d $Scratch -At -F " " -c $query
    if ($LASTEXITCODE -ne 0 -or -not $rows) { throw "the restored database could not be read" }
    Log "organization forms members documents staff"
    foreach ($row in $rows) { Log "  $row" }
    Log "OK: the dump restores"
}
catch {
    $failed = $true
    Log "FAILED: $($_.Exception.Message)"
}
finally {
    try { Drop-Scratch } catch { Log "could not drop ${Scratch}: $($_.Exception.Message)" }
}
if ($failed) { exit 1 }
