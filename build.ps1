param([switch]$Clean)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython -PathType Leaf)) {
    throw 'Python environment missing. Run: py -3 -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt'
}
& $taskPython -c 'import PyInstaller' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller missing. Run: .venv\Scripts\python.exe -m pip install pyinstaller'
}
& $taskPython -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"
$taskBuildArgs = @()
if ($Clean) { $taskBuildArgs += '--clean' }
& $taskPython -m PyInstaller @taskBuildArgs --noconfirm --windowed --onedir --name SnipTranslate --collect-submodules winrt --collect-data winrt --collect-submodules comtypes.gen --collect-data comtypes --collect-all rapidocr --collect-binaries onnxruntime --copy-metadata rapidocr --copy-metadata onnxruntime run.py
if ($LASTEXITCODE -ne 0) {
    throw 'Packaging failed. See PyInstaller output above.'
}
Write-Host 'Ready: dist\SnipTranslate\SnipTranslate.exe'
# Qt uses the Windows ICU API. Foreign ICU libraries found on PATH (for
# example Poppler's ICU) use incompatible exports and must not shadow it.
foreach ($taskIcuName in @('icuuc.dll', 'icudt78.dll')) {
    $taskIcuPath = Join-Path $PSScriptRoot ('dist\SnipTranslate\_internal\' + $taskIcuName)
    if (Test-Path -LiteralPath $taskIcuPath -PathType Leaf) {
        Move-Item -LiteralPath $taskIcuPath -Destination ($taskIcuPath + '.excluded') -Force
    }
}
Write-Host 'Distribute the entire dist\SnipTranslate directory.'
