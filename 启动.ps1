<#
.SYNOPSIS
  MPV Config Builder 启动器（源码运行 · Web UI）
.DESCRIPTION
  起一个本地服务并自动打开浏览器。只用 Python 标准库，不需要 pip install。
  2026-10-14 由 启动.bat 转换而来 —— 工程规则要求脚本入口统一 Pwsh，
  仓库里不再保留任何 .bat / .cmd（见 AGENTS.md §2.4）。
.NOTES
  编码约定与 .bat 时代相反：**UTF-8 必须带 BOM + CRLF**。
  带 BOM 是因为 Windows PowerShell 5.1 靠 BOM 识别 UTF-8（否则中文乱码），
  Pwsh 7 两种都认。用工具改完本文件后必须跑 python tools\build.py ps1。
  运行方式：右键 →「使用 PowerShell 运行」，或终端里 pwsh -File .\启动.ps1
  （执行策略被拦时怎么办，见 README「从源码跑」一节）。
#>
[CmdletBinding()]
param()

# 中文输出不乱码：终端默认代码页是 GBK（936），显式切成 UTF-8
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }

# 回到仓库根：右键运行时当前目录可能停在别处（桌面、System32……）
Set-Location -LiteralPath $PSScriptRoot

Write-Host '正在启动 MPV Config Builder ...'
Write-Host ''

if (-not (Test-Path -LiteralPath 'webui\server.py')) {
    Write-Host '[启动失败] 找不到 webui\server.py'
    Write-Host "当前目录：$((Get-Location).Path)"
    Write-Host '请确认是在解压出来的项目根目录里运行本文件。'
    Read-Host '按回车退出'
    exit 1
}

# 找 Python：先 python，再 py -3。
# 本机 py -3 会退出 103（AGENTS.md §2.2），所以 python 优先；
# 只装了 python.org 启动器、没把 python 加进 PATH 的机器上，py -3 是兜底。
$runner = $null
foreach ($spec in @(@('python'), @('py', '-3'))) {
    if (-not (Get-Command $spec[0] -ErrorAction SilentlyContinue)) { continue }
    if ($spec.Count -gt 1) { & $spec[0] $spec[1] -c 'import sys' } else { & $spec[0] -c 'import sys' }
    if ($LASTEXITCODE -eq 0) { $runner = $spec; break }
}

if (-not $runner) {
    Write-Host '[启动失败] 没找到能用的 Python 3。'
    Write-Host ''
    Write-Host '   已经试过 python 和 py -3，两个都跑不起来。'
    Write-Host '   想从源码跑：去 python.org 装一个，安装时记得勾选 "Add Python to PATH"。'
    Write-Host '   只是想把软件用起来：装 Electron 桌面版就行，不需要 Python。'
    Read-Host '按回车退出'
    exit 1
}

Write-Host "使用解释器：$($runner -join ' ')"
if ($runner.Count -gt 1) { & $runner[0] $runner[1] 'webui\server.py' } else { & $runner[0] 'webui\server.py' }
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '[启动失败] Python 报了错，往上翻看具体信息。'
    Write-Host '常见原因：core\ 或 data\ 目录缺失（是不是只复制了部分文件？）'
    Read-Host '按回车退出'
    exit 1
}
