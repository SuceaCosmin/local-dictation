param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# 1. Version from pyproject.toml
$version = (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Building Local Dictation $version"

# 2. Bundled model (cached between builds)
$model = Join-Path $root "packaging\model-cache\base.en"
$required = "config.json", "model.bin", "tokenizer.json"
$complete = -not ($required | Where-Object { -not (Test-Path (Join-Path $model $_)) })
if (-not $complete) {
    if (Test-Path $model) { Remove-Item $model -Recurse -Force }  # drop a partial earlier download
    Write-Host "Fetching base.en model..."
    poetry run python -c "from faster_whisper.utils import download_model; download_model('base.en', output_dir=r'$model')"
    if ($LASTEXITCODE -ne 0) { throw "model download failed" }
}

# 3. Freeze, then prove the frozen exe is complete
$out = Join-Path $root "build\pyinstaller"
poetry run pyinstaller packaging\local-dictation.spec --noconfirm --distpath "$out\dist" --workpath "$out\work"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$exe = Join-Path $out "dist\LocalDictation\LocalDictation.exe"
$result = Join-Path $out "selftest.txt"
Remove-Item $result -ErrorAction SilentlyContinue
# Offline: any fallback to the Hugging Face hub (e.g. a missing tokenizer) must fail the build.
$env:HF_HUB_OFFLINE = "1"
Start-Process $exe -ArgumentList "--self-test", "`"$result`"" -Wait
Remove-Item Env:HF_HUB_OFFLINE
$text = if (Test-Path $result) { Get-Content $result -Raw } else { "no result file (frozen exe crashed)" }
if (-not $text.StartsWith("OK")) { throw "frozen self-test failed: $text" }
if ($text -notmatch "models") { throw "frozen build is not using the bundled model: $text" }
Write-Host "Frozen self-test: $text"
$size = (Get-ChildItem "$out\dist\LocalDictation" -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Frozen folder size: {0:N0} MB" -f $size)

if ($SkipInstaller) { return }

# 4. Installer
$iscc = @(
    (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source,
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install --id JRSoftware.InnoSetup -e" }
& $iscc "/DAppVersion=$version" "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
$setup = Join-Path $root "dist\LocalDictation-$version-Setup.exe"
Write-Host ("Installer: {0} ({1:N0} MB)" -f $setup, ((Get-Item $setup).Length / 1MB))
