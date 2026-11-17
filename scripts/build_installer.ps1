# 一键出 Windows 安装包：Python 后端 -> Tauri 外壳 -> 安装器。
# 用法（仓库根目录）：powershell -File scripts\build_installer.ps1
# 可选：$env:MPVCB_BUILD_PYTHON 指定带 PyInstaller 的 Python（默认 python）。
# 说明见 docs\安装包产线.md。

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$py = $env:MPVCB_BUILD_PYTHON
if (-not $py) { $py = 'python' }

Write-Host '[1/3] 打 Python 后端（PyInstaller onedir）'
& $py tools\build.py backend
if ($LASTEXITCODE -ne 0) { throw '后端打包失败：先确认这个 Python 装了 pyinstaller（3.12 / 3.13）' }

Write-Host '[2/3] 把后端放进 Tauri 资源目录'
$src = Join-Path $root 'dist\MPVConfigBuilderBackend'
$dst = Join-Path $root 'tauri\src-tauri\backend'
if (-not (Test-Path -LiteralPath (Join-Path $src 'MPVConfigBuilderBackend.exe'))) {
    throw "没找到后端产物：$src"
}
if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
Copy-Item -LiteralPath $src -Destination $dst -Recurse

Write-Host '[3/3] 打 Tauri 安装器'
Push-Location -LiteralPath (Join-Path $root 'tauri')
try {
    cargo tauri build
    if ($LASTEXITCODE -ne 0) { throw 'Tauri 打包失败' }
} finally {
    Pop-Location
}

$bundle = Join-Path $root 'tauri\src-tauri\target\release\bundle'
Get-ChildItem -LiteralPath $bundle -Recurse -File -Include *.exe, *.msi |
    Select-Object FullName, @{n = 'MB'; e = { [math]::Round($_.Length / 1048576, 1) } }
