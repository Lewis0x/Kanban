#Requires -Version 5.1
# 一键启动 Kanban 看板（PowerShell）
# 用法: 在 Kanban 目录执行 .\start_kanban.ps1
# 若提示无法运行脚本: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "未找到 python，请先安装 Python 3 并加入 PATH。"
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "正在创建虚拟环境 .venv ..."
    & python -m venv (Join-Path $PSScriptRoot ".venv")
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
}

Write-Host "正在安装/更新依赖..."
& $venvPython -m pip install -q -r (Join-Path $PSScriptRoot "requirements.txt")

Write-Host ""
Write-Host "========================================"
Write-Host "  看板已启动"
Write-Host "  浏览器打开: http://127.0.0.1:5000"
Write-Host "  按 Ctrl+C 停止服务"
Write-Host "========================================"
Write-Host ""

& $venvPython -m flask --app app.main run --debug
