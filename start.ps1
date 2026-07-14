# 心动实验室 —— 一键启动（Windows）
# 由 start.bat 调用。真正的逻辑都在这里：PowerShell 能正确处理中文，cmd 的 .bat 不能。

$ErrorActionPreference = 'Stop'
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# Python 在中文 Windows 上默认用 GBK 输出，中文日志会变乱码。
$env:PYTHONIOENCODING = 'utf-8'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root 'backend'
$FrontendDir = Join-Path $Root 'frontend'
$VenvPy = Join-Path $BackendDir '.venv\Scripts\python.exe'
$PidFile = Join-Path $Root '.running-pids.txt'

function Write-Step($msg) { Write-Host "  $msg" -ForegroundColor Cyan }
function Write-Fail($msg) { Write-Host "  [x] $msg" -ForegroundColor Red }
function Write-Note($msg) { Write-Host "      $msg" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Magenta
Write-Host "     心动实验室 —— 启动中" -ForegroundColor Magenta
Write-Host "  ============================================" -ForegroundColor Magenta
Write-Host ""

# ---------- 1. 检查运行环境 ----------
$pythonCmd = $null
foreach ($c in @('python', 'python3')) {
    $found = Get-Command $c -ErrorAction SilentlyContinue
    if ($found) {
        # 需要 3.11+：代码用了 StrEnum、X | Y 类型标注等新语法
        & $c -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonCmd = $found.Source; break }
    }
}
if (-not $pythonCmd) {
    Write-Fail "没有找到 Python 3.11 或更新版本。"
    Write-Host ""
    Write-Note "请先安装 Python： https://www.python.org/downloads/"
    Write-Note "安装时请务必勾选 「Add Python to PATH」。"
    Write-Host ""
    exit 1
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Fail "没有找到 Node.js。"
    Write-Host ""
    Write-Note "请先安装 Node.js 20 或更新版本： https://nodejs.org/"
    Write-Host ""
    exit 1
}
$nodeMajor = [int](& node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 20) {
    Write-Fail "Node.js 版本过低（当前 $(& node -v)），需要 20 或更新版本。"
    Write-Host ""
    exit 1
}

# ---------- 2. 后端依赖 ----------
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Step "[1/4] 首次运行，正在准备后端环境..."
    Write-Note "这一步需要 3-5 分钟，只有第一次需要，请耐心等待。"
    Write-Host ""
    & $pythonCmd -m venv (Join-Path $BackendDir '.venv')
    if ($LASTEXITCODE -ne 0) { Write-Fail "创建 Python 虚拟环境失败。"; exit 1 }

    & $VenvPy -m pip install --upgrade pip --quiet
    Write-Note "正在下载依赖（走清华镜像加速）..."
    & $VenvPy -m pip install -r (Join-Path $BackendDir 'requirements.txt') --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple/
    if ($LASTEXITCODE -ne 0) {
        Write-Note "镜像源失败，改用官方源重试..."
        & $VenvPy -m pip install -r (Join-Path $BackendDir 'requirements.txt') --quiet
        if ($LASTEXITCODE -ne 0) { Write-Fail "后端依赖安装失败，请检查网络连接。"; exit 1 }
    }
} else {
    Write-Step "[1/4] 后端环境已就绪"
}

# ---------- 3. 前端依赖 + 构建 ----------
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir 'node_modules'))) {
    Write-Step "[2/4] 首次运行，正在准备前端环境（约 1-2 分钟）..."
    Push-Location $FrontendDir
    & npm install --no-audit --no-fund
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { Write-Fail "前端依赖安装失败，请检查网络连接。"; exit 1 }
} else {
    Write-Step "[2/4] 前端环境已就绪"
}

if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir '.next'))) {
    Write-Step "[3/4] 首次运行，正在构建前端（约 1-3 分钟，只有第一次需要）..."
    Push-Location $FrontendDir
    & npm run build
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { Write-Fail "前端构建失败。"; exit 1 }
} else {
    Write-Step "[3/4] 前端已构建"
}

# ---------- 4. 初始化数据库并启动 ----------
Write-Step "[4/4] 正在启动服务..."
& $VenvPy (Join-Path $BackendDir 'scripts\init_db.py')
if ($LASTEXITCODE -ne 0) { Write-Fail "数据库初始化失败。"; exit 1 }

# 先清掉上一次可能残留的进程，避免端口被占。
if (Test-Path -LiteralPath $PidFile) {
    foreach ($oldPid in (Get-Content -LiteralPath $PidFile)) {
        try { Stop-Process -Id ([int]$oldPid) -Force -ErrorAction Stop } catch {}
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

$backend = Start-Process -FilePath $VenvPy `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory $BackendDir -WindowStyle Minimized -PassThru

$frontend = Start-Process -FilePath 'cmd.exe' `
    -ArgumentList '/c', 'npm', 'run', 'start' `
    -WorkingDirectory $FrontendDir -WindowStyle Minimized -PassThru

# 记下 PID 供 stop.ps1 精确关闭，避免误杀用户自己的 python / node。
Set-Content -LiteralPath $PidFile -Value @($backend.Id, $frontend.Id) -Encoding ascii

Write-Host ""
Write-Note "正在等待服务就绪..."

# 轮询健康检查：就绪前打开浏览器只会看到报错页。
$ready = $false
foreach ($i in 1..60) {
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 | Out-Null
        $ready = $true
        break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
    Write-Fail "后端启动超时。请查看最小化的后端窗口里的报错信息。"
    exit 1
}

# 前端 next start 比后端稍慢一点
$frontendReady = $false
foreach ($i in 1..30) {
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:3000' -TimeoutSec 2 -UseBasicParsing | Out-Null
        $frontendReady = $true
        break
    } catch { Start-Sleep -Seconds 1 }
}
if (-not $frontendReady) {
    Write-Fail "前端启动超时。请查看最小化的前端窗口里的报错信息。"
    exit 1
}

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Green
Write-Host "     启动完成！浏览器即将打开" -ForegroundColor Green
Write-Host ""
Write-Host "     游戏地址： http://127.0.0.1:3000" -ForegroundColor Green
Write-Host "     首次使用请在网页上填入你的大模型信息" -ForegroundColor Green
Write-Host ""
Write-Host "     停止游戏：双击 stop.bat" -ForegroundColor Green
Write-Host "  ============================================" -ForegroundColor Green
Write-Host ""

Start-Process 'http://127.0.0.1:3000'
Start-Sleep -Seconds 3
exit 0
