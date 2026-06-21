# tools/extract-tools.ps1
# ---------------------------------------------------------------
# fetch-tools.ps1 ile indirilmis arsivleri ilgili tools/<name>/
# klasorlerine acar. ZIP -> Expand-Archive (powershell native).
# 7Z   -> tar -xf (windows bsdtar libarchive 7z support).
#
# Kullanim:
#   pwsh -File C:\Modding\tools\extract-tools.ps1
#
# Cikti:
#   tools/<name>/<extracted files>
#   tools/_extract-log.txt
#
# Idempotent: arsiv yoksa skip eder. Extracted dosyalar uzerine
# yazar (Force).
# ---------------------------------------------------------------

$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

$toolsDir = $PSScriptRoot
$logFile  = Join-Path $toolsDir "_extract-log.txt"

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

Set-Content -Path $logFile -Value ("EXTRACT LOG -- {0}`n" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))

# Discover archives in each tool folder.
$entries = Get-ChildItem -Path $toolsDir -Directory | ForEach-Object {
    $arch = Get-ChildItem -Path $_.FullName -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.zip', '.7z' } |
            Select-Object -First 1
    if ($arch) {
        [pscustomobject]@{ Tool = $_.Name; Archive = $arch.FullName; Dir = $_.FullName }
    }
}

if ($entries.Count -eq 0) {
    Log "no archives found under $toolsDir"
    return
}

foreach ($e in $entries) {
    Log ("=== {0} ({1}) ===" -f $e.Tool, [System.IO.Path]::GetFileName($e.Archive))
    try {
        if ($e.Archive -match '\.zip$') {
            Expand-Archive -Path $e.Archive -DestinationPath $e.Dir -Force
            Log "  zip extracted (Expand-Archive)"
        } elseif ($e.Archive -match '\.7z$') {
            $prev = $LASTEXITCODE
            tar -xf $e.Archive -C $e.Dir 2>&1 | ForEach-Object { Log ("    tar: {0}" -f $_) }
            if ($LASTEXITCODE -ne 0) {
                Log ("  TAR FAILED with exit {0}" -f $LASTEXITCODE)
                continue
            }
            Log "  7z extracted (tar/libarchive)"
        }
    } catch {
        Log ("  ERROR: {0}" -f $_.Exception.Message)
    }
}

# Discover entry-point .exe paths so MANIFEST can be filled in.
Log ""
Log "=== EXE INDEX (for MANIFEST.md binary_path) ==="
foreach ($d in (Get-ChildItem $toolsDir -Directory | Sort-Object Name)) {
    $exes = Get-ChildItem -Path $d.FullName -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notmatch 'unins' } |
            Select-Object -First 8
    if ($exes) {
        Log ("  [{0}]" -f $d.Name)
        foreach ($x in $exes) {
            $rel = $x.FullName.Substring($toolsDir.Length + 1).Replace("\","/")
            $sz  = [math]::Round($x.Length / 1MB, 2)
            Log ("    {0}  ({1} MB)" -f $rel, $sz)
        }
    }
}

Log "=== DONE ==="
