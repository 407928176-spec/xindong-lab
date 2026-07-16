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

# winget 上 Python 没有「永远指向最新版」的单一包 ID（不像 Node 有 OpenJS.NodeJS），
# 每个小版本各自一个包（Python.Python.3.12、3.13、3.14……），所以要自己去查一遍目录、
# 挑数字最大的那个。查不到就返回 $null，调用方要有一个写死的稳妥版本兜底——不能因为
# 这一步查询失败，就把原本能用的自动安装也搭进去。
function Get-LatestPythonWingetId {
    try {
        $raw = & winget search "Python.Python.3" --source winget 2>$null
    } catch {
        return $null
    }
    if (-not $raw) { return $null }

    $candidates = @()
    foreach ($line in $raw) {
        if ($line -match '(Python\.Python\.3\.(\d+))\s') {
            $candidates += [PSCustomObject]@{ Id = $Matches[1]; Minor = [int]$Matches[2] }
        }
    }
    if ($candidates.Count -eq 0) { return $null }
    return ($candidates | Sort-Object Minor -Descending | Select-Object -First 1).Id
}

# 装完 winget 包之后，系统 PATH 已经变了，但当前这个 PowerShell 进程的 $env:Path
# 还是启动时的旧快照。从注册表重新拼一遍，装完当场就能用，不用再双击一次。
function Update-PathFromRegistry {
    $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machinePath, $userPath) -join ';'
}

# winget 装 Python 是从 python.org 官方站点下载安装包的，国内网络访问经常很慢、
# 感觉像卡住了。华为云维护着一份跟官网目录结构一模一样的镜像，命中的话通常快很多，
# 而且是我们自己拿 Invoke-WebRequest 下载文件，能看到真实的下载百分比（这点 winget
# 的静默安装做不到，它不往外报进度）。
function Get-LatestPythonVersionFromMirror {
    param([string]$MirrorBase = "https://mirrors.huaweicloud.com/python/")
    try {
        $html = Invoke-WebRequest -Uri $MirrorBase -TimeoutSec 10 -UseBasicParsing
    } catch {
        return $null
    }
    $versions = [regex]::Matches($html.Content, 'href="(\d+\.\d+\.\d+)/"') | ForEach-Object { $_.Groups[1].Value }
    if (-not $versions) { return $null }
    $sorted = $versions | ForEach-Object {
        $p = $_.Split('.')
        [PSCustomObject]@{ Version = $_; Major = [int]$p[0]; Minor = [int]$p[1]; Patch = [int]$p[2] }
    } | Sort-Object Major, Minor, Patch -Descending

    # 目录名存在不代表正式版已经放出来——新版本发布前，镜像会提前建好目录，
    # 里面只有 alpha / beta 预发布材料，这时正式的 Windows 安装包文件还没传上去，
    # 直接拼 URL 下载会 404。必须反过来实测文件是不是真的在，不在就退到下一个
    # 版本号，直到找到一个真能下载的（只探测前 5 个，避免镜像大范围异常时卡太久）。
    foreach ($candidate in ($sorted | Select-Object -First 5)) {
        $testUrl = "$MirrorBase$($candidate.Version)/python-$($candidate.Version)-amd64.exe"
        try {
            $resp = Invoke-WebRequest -Uri $testUrl -Method Head -TimeoutSec 8 -UseBasicParsing
            if ($resp.StatusCode -eq 200) { return $candidate.Version }
        } catch {
            continue
        }
    }
    return $null
}

# 从镜像下载官方安装包并静默装上。失败（镜像连不上、探测不到可用版本、下载失败、
# 装的时候出错）一律返回 $false，调用方会自动退回 winget 那一套，不会卡在这里。
function Install-PythonFromMirror {
    param([string]$MirrorBase = "https://mirrors.huaweicloud.com/python/")

    $version = Get-LatestPythonVersionFromMirror -MirrorBase $MirrorBase
    if (-not $version) { return $false }

    $fileName = "python-$version-amd64.exe"
    $url = "$MirrorBase$version/$fileName"
    $installerPath = Join-Path $env:TEMP $fileName

    Write-Step "正在从国内镜像下载 Python $version 安装包……"
    try {
        Invoke-WebRequest -Uri $url -OutFile $installerPath -TimeoutSec 300 -UseBasicParsing
    } catch {
        Write-Note "镜像下载失败，改用 winget 安装。"
        return $false
    }

    Write-Step "下载完成，正在安装（会弹出一次 Windows 管理员确认框）……"
    try {
        # 官方安装包的标准静默参数：InstallAllUsers 装到系统目录、PrependPath 自动
        # 加进 PATH（就是网页向导里反复提醒手动装时必须勾选的那个选项）、
        # Include_test=0 跳过用不上的标准库测试套件，省点安装时间。
        $proc = Start-Process -FilePath $installerPath `
            -ArgumentList @('/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_test=0') `
            -Wait -PassThru
    } catch {
        Write-Note "安装程序启动失败，改用 winget 安装。"
        return $false
    } finally {
        Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    }

    if ($proc.ExitCode -ne 0) {
        Write-Note "安装失败（退出码 $($proc.ExitCode)），改用 winget 安装。"
        return $false
    }

    Update-PathFromRegistry
    Write-Step "Python $version 安装完成。"
    return $true
}

# winget 装 Node 同样是从官方 nodejs.org 下载的，实测同一个网络环境下，连它的下载
# CDN 都要 10 秒以上（对比华为云镜像 2 秒多），跟 Python 是同一个毛病。这份镜像连
# 官方的版本元数据 index.json 都原样镜像了，直接拿它判断哪个版本是长期支持版（LTS）
# 最准确——不能简单挑版本号最大的那个，Node 有「当前版」和「长期支持版」两条线，
# 项目这里要的是稳定的 LTS，跟 winget 那边用 OpenJS.NodeJS.LTS 保持一致。
function Get-LatestNodeLtsVersionFromMirror {
    param([string]$MirrorBase = "https://mirrors.huaweicloud.com/nodejs/")
    try {
        # 这个镜像给 index.json 打的 Content-Type 是 application/octet-stream，不是
        # text/json——Windows PowerShell 5.1 的 Invoke-WebRequest 只认得 text 系的
        # 类型才会把 .Content 解成字符串，认不出来就直接给一个原始字节数组，这时候
        # 拿去 ConvertFrom-Json 会把每个字节当成一条数据，解析结果全是错的还不报错。
        # Invoke-RestMethod 不看这个头，直接按 JSON 处理，更稳。
        $entries = Invoke-RestMethod -Uri "${MirrorBase}index.json" -TimeoutSec 10
    } catch {
        return $null
    }
    $ltsEntries = $entries | Where-Object { $_.lts }
    if (-not $ltsEntries) { return $null }

    $sorted = $ltsEntries | ForEach-Object {
        $v = $_.version.TrimStart('v')
        $p = $v.Split('.')
        [PSCustomObject]@{ Version = $v; Major = [int]$p[0]; Minor = [int]$p[1]; Patch = [int]$p[2] }
    } | Sort-Object Major, Minor, Patch -Descending

    # index.json 里列着的版本，镜像上不一定每一份安装包都同步全了，跟 Python 那边
    # 一样反过来实测文件在不在，不在就退到下一个版本号。
    foreach ($candidate in ($sorted | Select-Object -First 5)) {
        $testUrl = "${MirrorBase}v$($candidate.Version)/node-v$($candidate.Version)-x64.msi"
        try {
            $resp = Invoke-WebRequest -Uri $testUrl -Method Head -TimeoutSec 8 -UseBasicParsing
            if ($resp.StatusCode -eq 200) { return $candidate.Version }
        } catch {
            continue
        }
    }
    return $null
}

# 从镜像下载官方 MSI 并静默装上。失败一律返回 $false，调用方会自动退回 winget。
function Install-NodeFromMirror {
    param([string]$MirrorBase = "https://mirrors.huaweicloud.com/nodejs/")

    $version = Get-LatestNodeLtsVersionFromMirror -MirrorBase $MirrorBase
    if (-not $version) { return $false }

    $fileName = "node-v$version-x64.msi"
    $url = "${MirrorBase}v$version/$fileName"
    $installerPath = Join-Path $env:TEMP $fileName

    Write-Step "正在从国内镜像下载 Node.js v$version 安装包……"
    try {
        Invoke-WebRequest -Uri $url -OutFile $installerPath -TimeoutSec 300 -UseBasicParsing
    } catch {
        Write-Note "镜像下载失败，改用 winget 安装。"
        return $false
    }

    Write-Step "下载完成，正在安装（会弹出一次 Windows 管理员确认框）……"
    try {
        # 官方 MSI 默认就会把 node 加进 PATH，不用像 Python 那样额外传参数。
        $proc = Start-Process -FilePath "msiexec.exe" `
            -ArgumentList @('/i', "`"$installerPath`"", '/quiet', '/norestart') `
            -Wait -PassThru
    } catch {
        Write-Note "安装程序启动失败，改用 winget 安装。"
        return $false
    } finally {
        Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
    }

    if ($proc.ExitCode -ne 0) {
        # 常见原因之一：电脑上已经有一个不在 PATH 里、但版本更新的 Node 残留注册
        # 记录，官方安装包自带的版本检查会直接拒装。这种情况交给 winget 试试，
        # 也不行的话最终会被下面的 Get-Command node 兜底检测出来，不会静默失败。
        Write-Note "安装失败（退出码 $($proc.ExitCode)），改用 winget 安装。"
        return $false
    }

    Update-PathFromRegistry
    Write-Step "Node.js v$version 安装完成。"
    return $true
}

# winget 静默安装时，尤其是真正往系统里写文件的那一段，经常有几十秒完全没有任何
# 输出——这是安装程序本身的限制，不是能从外面拿到精确进度百分比的东西。硬做一个假的
# 进度条只会更误导人，所以这里退而求其次：每隔几秒钟报一次「还在装、已经过了多久」，
# 至少让人知道它没死，比长时间死寂要好。
#
# 用 -RedirectStandardOutput 把 winget 自己的输出接到文件里、不让它直接打进控制台，
# 是为了避免它的进度条（靠光标控制码原地刷新）跟我们自己这行心跳提示互相打架、糊成
# 一团看不清字——两边同时喊麻烦，就让我们这边喊清楚话，把 winget 那边先摁住。
function Invoke-WithHeartbeat {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$DisplayName,
        [int]$HeartbeatSeconds = 15
    )
    $outLog = [System.IO.Path]::GetTempFileName()
    $errLog = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
            -RedirectStandardOutput $outLog -RedirectStandardError $errLog -NoNewWindow -PassThru
        # Start-Process -PassThru 返回的 Process 对象，如果不在这里先摸一下 .Handle，
        # 进程退出后 .ExitCode 有很大概率读出来是空的——这是 .NET Process 类一个老毛病。
        $proc.Handle | Out-Null

        $elapsed = 0
        while (-not $proc.HasExited) {
            Start-Sleep -Seconds $HeartbeatSeconds
            $elapsed += $HeartbeatSeconds
            Write-Note "仍在安装 $DisplayName ……已用时约 $elapsed 秒，这是正常现象，请不要关闭这个窗口。"
        }
        $proc.WaitForExit()
        return $proc.ExitCode
    } finally {
        Remove-Item -LiteralPath $outLog, $errLog -Force -ErrorAction SilentlyContinue
    }
}

# 缺 Python / Node 时：有 winget 就问一声要不要自动装（会弹一次 Windows 管理员确认框）；
# 没有 winget，或者用户不想自动装，就直接带去官网下载页，让用户自己走安装向导。
#
# $PreferredInstaller（可选）：装之前先试这个（目前只有 Python 会传，走国内镜像直接
# 下载），成功就不用再碰 winget；失败了照样自动退回下面这套 winget 流程，双保险。
function Install-Runtime-Or-Guide {
    param(
        [string]$DisplayName,
        [string]$WingetId,
        [string]$DownloadUrl,
        [string]$ExtraNote = "",
        [scriptblock]$PreferredInstaller = $null
    )
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    $winget = Get-Command winget -ErrorAction SilentlyContinue

    if (-not $winget -and -not $PreferredInstaller) {
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

    if ($PreferredInstaller) {
        if (& $PreferredInstaller) { return $true }
        Write-Note "改用 winget 继续尝试安装 $DisplayName ……"
    }

    if (-not $winget) {
        [System.Windows.Forms.MessageBox]::Show(
            "$DisplayName 自动安装失败，即将为你打开官网下载页，请手动安装。$ExtraNote",
            "心动实验室 - 自动安装失败",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
        Start-Process $DownloadUrl
        return $false
    }

    Write-Step "正在通过 winget 安装 $DisplayName（第一次可能要几分钟，请留意可能弹出的管理员确认框）..."
    $wingetExitCode = Invoke-WithHeartbeat -FilePath "winget" -DisplayName $DisplayName -ArgumentList @(
        'install', '--id', $WingetId, '-e', '--silent',
        '--accept-package-agreements', '--accept-source-agreements'
    )
    if ($wingetExitCode -ne 0) {
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
    # 优先查 winget 目录里当前最新的 Python 版本；查不到（网络问题、winget 版本太旧
    # 等）就退回一个已知稳妥、生态兼容性验证过的版本，不能让这一步查询失败就把整个
    # 自动安装带崩。
    $latestPythonId = Get-LatestPythonWingetId
    if ($latestPythonId) {
        $pythonWingetId = $latestPythonId
        $pythonDisplayName = "Python " + ($latestPythonId -replace 'Python\.Python\.', '')
    } else {
        $pythonWingetId = "Python.Python.3.12"
        $pythonDisplayName = "Python 3.12"
    }
    $installed = Install-Runtime-Or-Guide -DisplayName $pythonDisplayName -WingetId $pythonWingetId `
        -DownloadUrl "https://www.python.org/downloads/" `
        -ExtraNote "安装时请务必勾选「Add Python to PATH」。" `
        -PreferredInstaller { Install-PythonFromMirror }
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
        -DownloadUrl "https://nodejs.org/" `
        -PreferredInstaller { Install-NodeFromMirror }
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
