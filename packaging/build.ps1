param([switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# 1. Version from pyproject.toml
$version = (Select-String -Path "pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Building Local Dictation $version"

# 2. Bundled model (cached between builds)
$model = Join-Path $root "packaging\model-cache\base.en"
if (-not (Test-Path (Join-Path $model "model.bin"))) {
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
Start-Process $exe -ArgumentList "--self-test", "`"$result`"" -Wait
$text = if (Test-Path $result) { Get-Content $result -Raw } else { "no result file (frozen exe crashed)" }
if (-not $text.StartsWith("OK")) { throw "frozen self-test failed: $text" }
if ($text -notmatch "models") { throw "frozen build is not using the bundled model: $text" }
Write-Host "Frozen self-test: $text"
$size = (Get-ChildItem "$out\dist\LocalDictation" -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("Frozen folder size: {0:N0} MB" -f $size)

if ($SkipInstaller) { return }
# 4. Installer stage is added in Task 5.
