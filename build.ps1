param(
    [string]$PkgPython = "$env:USERPROFILE\anaconda3\envs\pkg\python.exe"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path $PkgPython)) { throw "找不到 python：$PkgPython" }
& $PkgPython -c "import PyInstaller, onnxruntime"
if ($LASTEXITCODE -ne 0) { throw "缺 PyInstaller 或 onnxruntime" }
foreach ($m in @("proposer.onnx", "judge.onnx", "judge_disc.onnx", "detector.onnx", "vocab.txt")) {
    if (-not (Test-Path (Join-Path "models" $m))) { throw "models\ 缺 $m（從 release zip 的 tcsc\_internal\models\ 取）" }
}

& $PkgPython -m PyInstaller --noconfirm --clean --distpath dist --workpath build tcsc\tcsc.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失敗" }

$tcl = Get-ChildItem "dist\tcsc" -Recurse -Filter "tcl86t.dll" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($tcl -and (Get-FileHash $tcl.FullName -Algorithm MD5).Hash -eq "8C5EA7887E6C93025DC4836E4EB4560B") {
    Write-Warning "tcl86t.dll 版本不對（8.6.14），Tk 視窗會崩：請用 Tcl 8.6.15 的環境重建"
}
foreach ($m in @("proposer.onnx", "judge.onnx", "judge_disc.onnx", "detector.onnx", "vocab.txt")) {
    if (-not (Test-Path (Join-Path "dist\tcsc\_internal\models" $m))) { throw "模型沒打包進去：$m" }
}
Write-Host "完成：dist\tcsc\tcsc.exe" -ForegroundColor Green
