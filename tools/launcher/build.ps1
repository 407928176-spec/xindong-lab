# 构建心动实验室 Windows 启动器（心动实验室.exe）。
#
# 用 Windows 自带的 .NET Framework C# 编译器（csc.exe），不依赖任何第三方打包工具，
# 也不要求开发机额外安装 SDK。产物是仓库根目录下的「心动实验室.exe」，图标取自
# tools/launcher/logo.ico（由 frontend/public/logo.png 生成，见同目录 README 说明）。
#
# 用法：在仓库根目录或本目录下执行
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools/launcher/build.ps1

chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"

$LauncherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $LauncherDir)

$CscCandidates = @(
    "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
    "$env:WINDIR\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)
$Csc = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $Csc) {
    Write-Host "找不到 csc.exe（.NET Framework 编译器），无法构建启动器。" -ForegroundColor Red
    Write-Host "这台机器可能缺少 .NET Framework 4.x，一般 Windows 10/11 都自带，请检查系统完整性。" -ForegroundColor Red
    exit 1
}

$SourceFile = Join-Path $LauncherDir "Launcher.cs"
$IconFile = Join-Path $LauncherDir "logo.ico"
$OutputExe = Join-Path $RepoRoot "心动实验室.exe"

Write-Host "使用编译器: $Csc"
Write-Host "输出文件: $OutputExe"

& $Csc `
    /nologo `
    /target:winexe `
    /platform:anycpu `
    "/out:$OutputExe" `
    "/win32icon:$IconFile" `
    /reference:System.Windows.Forms.dll `
    "$SourceFile"

if ($LASTEXITCODE -ne 0) {
    Write-Host "编译失败。" -ForegroundColor Red
    exit 1
}

Write-Host "构建完成：$OutputExe" -ForegroundColor Green
