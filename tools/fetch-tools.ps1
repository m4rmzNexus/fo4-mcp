# tools/fetch-tools.ps1
# ---------------------------------------------------------------
# FO4 modding tool'larını GitHub releases'ten otomatik indirir.
# Auth gerektirenler (Nexus, Bethesda.net) MANUAL-DOWNLOADS.txt'de.
#
# Kullanım:
#   pwsh -File C:\Modding\tools\fetch-tools.ps1
#
# Çıktı:
#   tools/<name>/<asset>  -> indirilen dosya
#   tools/_fetch-log.txt  -> her indirmenin versiyon, URL, hash bilgisi
#                            (MANIFEST.md elle bu log'tan doldurulur)
# ---------------------------------------------------------------

$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"   # Invoke-WebRequest hızlandırma

$repoRoot = Split-Path $PSScriptRoot -Parent
$toolsDir = Join-Path $repoRoot "tools"
$logFile  = Join-Path $toolsDir "_fetch-log.txt"

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

Set-Content -Path $logFile -Value ("FETCH LOG -- {0}`n" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))

# pattern: ilk eslesen asset alinir; -like wildcard.
# license: SPDX kodu; 'unknown' = LICENSE dosyasi yok (Nexus permissions).
$tools = @(
    # --- session 2 batch ---
    @{ name = "spriggit";    repo = "Mutagen-Modding/Spriggit";          pattern = "*CLI*.zip";      license = "GPL-3.0" }
    @{ name = "synthesis";   repo = "Mutagen-Modding/Synthesis";         pattern = "Synthesis*.zip"; license = "GPL-3.0" }
    @{ name = "mutagen";     repo = "Mutagen-Modding/Mutagen";           pattern = "*.zip";          license = "GPL-3.0" }
    @{ name = "caprica";     repo = "Orvid/Caprica";                     pattern = "*.7z";           license = "MIT" }
    @{ name = "champollion"; repo = "Orvid/Champollion";                 pattern = "*.zip";          license = "LGPL-3.0" }
    @{ name = "xedit";       repo = "TES5Edit/TES5Edit";                 pattern = "*xEdit*.7z";     license = "MPL-2.0" }
    @{ name = "classic";     repo = "evildarkarchon/CLASSIC-Fallout4";   pattern = "*.7z";           license = "unknown" }
    # mo2 removed: github release ships only -pdbs.7z (debug symbols),
    # actual binary is on nexus. moved to MANUAL-DOWNLOADS.txt.
    # @{ name = "mo2";         repo = "ModOrganizer2/modorganizer";        pattern = "*Mod.Organizer*.7z"; license = "GPL-3.0" }

    # --- session 2 expansion (auto-fetchable) ---
    # NOTE: BSArch (TES5Edit/BSArch), Cathedral Assets Optimizer
    # (Guekka/Cathedral-Assets-Optimizer), and BodySlide (no binary in
    # GitHub release) moved to MANUAL-DOWNLOADS.txt — repos either
    # 404 or ship source-only.
    @{ name = "loot";        repo = "loot/loot";                         pattern = "*win64*.7z";       license = "GPL-3.0" }
    @{ name = "nifskope";    repo = "fo76utils/nifskope";                pattern = "*win64qt6_clang*.7z"; license = "BSD-3-Clause" }
    @{ name = "wrye-bash";   repo = "wrye-bash/wrye-bash";               pattern = "*Standalone*.7z"; license = "GPL-3.0" }
)

$headers = @{ "User-Agent" = "fo4-mcp-fetch" }

foreach ($t in $tools) {
    Log ("=== {0} ({1}) ===" -f $t.name, $t.repo)
    try {
        $apiUrl  = "https://api.github.com/repos/$($t.repo)/releases/latest"
        $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 30
        Log ("  version: {0}    published: {1}" -f $release.tag_name, $release.published_at)

        $asset = $release.assets | Where-Object { $_.name -like $t.pattern } | Select-Object -First 1
        if (-not $asset) {
            Log ("  SKIP -- no asset matching '{0}'" -f $t.pattern)
            $names = ($release.assets | ForEach-Object { $_.name }) -join ', '
            Log ("  available: {0}" -f $names)
            continue
        }

        $targetDir = Join-Path $toolsDir $t.name
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

        $outFile = Join-Path $targetDir $asset.name
        $sizeMB  = [math]::Round($asset.size / 1MB, 1)
        Log ("  asset: {0} ({1} MB)" -f $asset.name, $sizeMB)
        Log ("  url:   {0}" -f $asset.browser_download_url)

        if (Test-Path $outFile) {
            Log "  EXISTS -- skipping download"
        } else {
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $outFile -Headers $headers -TimeoutSec 600
            Log "  downloaded OK"
        }

        $hash = (Get-FileHash $outFile -Algorithm SHA256).Hash
        Log ("  sha256: {0}" -f $hash)
        Log ("  license: {0}" -f $t.license)
    } catch {
        Log ("  ERROR: {0}" -f $_.Exception.Message)
    }
}

Log "=== DONE ==="
