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

# 双击「心动实验室.exe」时，start.ps1 是在一个全新的、没有人盯着的控制台窗口里跑的。
# 以前失败时直接 `exit 1`，窗口会跟着 powershell.exe 进程一起瞬间关掉，玩家连错误
# 信息是什么都看不清就没了（表现为"卡一下然后闪退"）。所以失败退出前一律停下来等一个按键。
#
# 只在真正的交互式控制台里等：这个脚本也会被自动化测试用管道 / 重定向的方式跑，
# 那种场景下 stdin 不是键盘，ReadKey 会永远等不到输入，把测试也一起卡死。
function Exit-Failed {
    param([int]$Code = 1)
    if (-not [Console]::IsInputRedirected) {
        Write-Host ""
        Write-Host "  按任意键关闭这个窗口..." -ForegroundColor DarkGray
        $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    }
    exit $Code
}

# 兜底：任何没被下面显式 try/catch 住的意外错误（比如权限问题、磁盘写满这类没预料到
# 的状况），也要走同一条「停下来等按键」的路，而不是让窗口带着一句看不清的报错消失。
trap {
    Write-Host ""
    Write-Fail "启动过程中出现意外错误：$($_.Exception.Message)"
    Exit-Failed
}

function Find-Python {
    foreach ($c in @('python', 'python3')) {
        $found = Get-Command $c -ErrorAction SilentlyContinue
        if ($found) {
            # 需要 3.11+：代码用了 StrEnum、X | Y 类型标注等新语法
            & $found.Source -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $found.Source }
        }
    }
    return $null
}

# 装完 winget 包之后，系统 PATH 已经变了，但当前这个 PowerShell 进程的 $env:Path
# 还是启动时的旧快照。从注册表重新拼一遍，装完当场就能用，不用再双击一次。
function Update-PathFromRegistry {
    $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machinePath, $userPath) -join ';'
}

# 缺 Python / Node 时：有 winget 就问一声要不要自动装（会弹一次 Windows 管理员确认框）；
# 没有 winget，或者用户不想自动装，就直接带去官网下载页，让用户自己走安装向导。
function Install-Runtime-Or-Guide {
    param(
        [string]$DisplayName,
        [string]$WingetId,
        [string]$DownloadUrl,
        [string]$ExtraNote = ""
    )
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    $winget = Get-Command winget -ErrorAction SilentlyContinue

    if (-not $winget) {
        [System.Windows.Forms.MessageBox]::Show(
            "心动实验室需要 $DisplayName，但这台电脑上没有检测到，也没有可用的自动安装工具（winget）。`n`n即将为你打开官网下载页，请手动安装。$ExtraNote",
            "心动实验室 - 缺少运行环境",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        Start-Process $DownloadUrl
        return $false
    }

    $choice = [System.Windows.Forms.MessageBox]::Show(
        "心动实验室需要 $DisplayName，但这台电脑上没有检测到。`n`n点「是」自动安装（会弹出 Windows 管理员确认框）；点「否」自己去官网下载安装。",
        "心动实验室 - 缺少运行环境",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question)
    if ($choice -ne [System.Windows.Forms.DialogResult]::Yes) {
        Start-Process $DownloadUrl
        return $false
    }

    Write-Step "正在通过 winget 安装 $DisplayName（第一次可能要几分钟，请留意可能弹出的管理员确认框）..."
    & winget install --id $WingetId -e --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        [System.Windows.Forms.MessageBox]::Show(
            "$DisplayName 自动安装失败，即将为你打开官网下载页，请手动安装。$ExtraNote",
            "心动实验室 - 自动安装失败",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        Start-Process $DownloadUrl
        return $false
    }
    Update-PathFromRegistry
    Write-Step "$DisplayName 安装完成。"
    return $true
}

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Magenta
Write-Host "     心动实验室 —— 启动中" -ForegroundColor Magenta
Write-Host "  ============================================" -ForegroundColor Magenta
Write-Host ""

# ---------- 1. 检查运行环境（缺了就问一下要不要自动装）----------
$pythonCmd = Find-Python
if (-not $pythonCmd) {
    $installed = Install-Runtime-Or-Guide -DisplayName "Python 3.12" -WingetId "Python.Python.3.12" `
        -DownloadUrl "https://www.python.org/downloads/" `
        -ExtraNote "安装时请务必勾选「Add Python to PATH」。"
    if ($installed) { $pythonCmd = Find-Python }
}
if (-not $pythonCmd) {
    Write-Fail "没有找到 Python 3.11 或更新版本。"
    Write-Host ""
    Write-Note "装好之后重新双击「心动实验室.exe」（或运行 start.bat）即可。"
    Write-Note "安装时请务必勾选 「Add Python to PATH」。"
    Write-Host ""
    Exit-Failed
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $installed = Install-Runtime-Or-Guide -DisplayName "Node.js" -WingetId "OpenJS.NodeJS.LTS" `
        -DownloadUrl "https://nodejs.org/"
    if (-not $installed -or -not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Fail "没有找到 Node.js。"
        Write-Host ""
        Write-Note "装好之后重新双击「心动实验室.exe」（或运行 start.bat）即可。"
        Write-Host ""
        Exit-Failed
    }
}
$nodeMajor = [int](& node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 20) {
    Write-Fail "Node.js 版本过低（当前 $(& node -v)），需要 20 或更新版本。"
    Write-Host ""
    Exit-Failed
}

# ---------- 2. 后端依赖 ----------
if (-not (Test-Path -LiteralPath $VenvPy)) {
    Write-Step "[1/4] 首次运行，正在准备后端环境..."
    Write-Note "这一步需要 3-5 分钟，只有第一次需要，请耐心等待。"
    Write-Host ""
    & $pythonCmd -m venv (Join-Path $BackendDir '.venv')
    if ($LASTEXITCODE -ne 0) { Write-Fail "创建 Python 虚拟环境失败。"; Exit-Failed }

    & $VenvPy -m pip install --upgrade pip --quiet
    Write-Note "正在下载依赖（走清华镜像加速）..."
    & $VenvPy -m pip install -r (Join-Path $BackendDir 'requirements.txt') --quiet -i https://pypi.tuna.tsinghua.edu.cn/simple/
    if ($LASTEXITCODE -ne 0) {
        Write-Note "镜像源失败，改用官方源重试..."
        & $VenvPy -m pip install -r (Join-Path $BackendDir 'requirements.txt') --quiet
        if ($LASTEXITCODE -ne 0) { Write-Fail "后端依赖安装失败，请检查网络连接。"; Exit-Failed }
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
    if (-not $ok) { Write-Fail "前端依赖安装失败，请检查网络连接。"; Exit-Failed }
} else {
    Write-Step "[2/4] 前端环境已就绪"
}

# 判断"构建过"要看 BUILD_ID 存不存在，不能只看 .next 目录存不存在：
# 只要 `npm run build` 真正跑起来过，.next 目录就会被创建，哪怕过程中失败或被中途打断
# （比如上一次启动失败、窗口被关掉）。BUILD_ID 是构建流程走到最后才写的文件，只有它在
# 才说明上次是真的构建成功了；否则会出现"看起来构建过，实际是个半成品，npm run start
# 起不来、一直卡在等服务就绪"的情况。
$buildIdPath = Join-Path $FrontendDir '.next\BUILD_ID'
if (-not (Test-Path -LiteralPath $buildIdPath)) {
    Write-Step "[3/4] 首次运行，正在构建前端（约 1-3 分钟，只有第一次需要）..."
    Push-Location $FrontendDir
    & npm run build
    $ok = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $buildIdPath)
    Pop-Location
    if (-not $ok) { Write-Fail "前端构建失败。"; Exit-Failed }
} else {
    Write-Step "[3/4] 前端已构建"
}

# ---------- 4. 初始化数据库并启动 ----------
Write-Step "[4/4] 正在启动服务..."
& $VenvPy (Join-Path $BackendDir 'scripts\init_db.py')
if ($LASTEXITCODE -ne 0) { Write-Fail "数据库初始化失败。"; Exit-Failed }

# 先清掉上一次可能残留的进程，避免端口被占。
if (Test-Path -LiteralPath $PidFile) {
    foreach ($oldPid in (Get-Content -LiteralPath $PidFile)) {
        try { Stop-Process -Id ([int]$oldPid) -Force -ErrorAction Stop } catch {}
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

# PID 文件之外还可能有孤儿进程（上次异常退出、或文件被删）。它们占着端口不放，
# 新起的服务会静默失败——旧进程还在响应，页面打得开，但跑的是上一版代码，
# 让人误以为「重启过了」。这里按端口反查，只清命令行里带本项目路径的进程，
# 玩家自己开的 node / python 不受影响。
foreach ($port in @(8000, 3000)) {
    foreach ($conn in (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        $procId = [int]$conn.OwningProcess
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -and
            $proc.CommandLine.IndexOf($Root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            Write-Note "清理上次残留的进程（端口 $port）..."
            try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
        }
    }
}
Start-Sleep -Milliseconds 500

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
    Exit-Failed
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
    Exit-Failed
}

# 服务已在监听，把「真正占着端口的那个进程」也记进 PID 文件。
# 上面记的是 Start-Process 拿到的父进程，但前端的进程链是 cmd → npm → node：
# 中间那层退出后，真正监听 3000 的 node 就成了孤儿，顺着父子关系再也找不到它，
# stop.bat 会漏杀、端口一直被占着，下次启动的新前端起不来（旧页面还能打开，
# 于是「明明重启了，跑的还是旧代码」）。直接把监听者的 PID 记下来最稳。
$listenerIds = @()
foreach ($port in @(8000, 3000)) {
    foreach ($conn in (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        $listenerIds += [int]$conn.OwningProcess
    }
}
Set-Content -LiteralPath $PidFile `
    -Value (@($backend.Id, $frontend.Id) + $listenerIds | Select-Object -Unique) -Encoding ascii

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
