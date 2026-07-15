# 心动实验室 —— 停止服务。由 stop.bat 调用。

chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root '.running-pids.txt'

# 递归收集整棵进程树。
# 必须递归到孙子进程：前端的进程链是 cmd → npm → node，真正监听 3000 端口的是最底下那个
# node。只杀直接子进程的话，端口会一直被占着，下次启动就起不来。
function Get-ProcessTreeIds([int]$RootId) {
    $ids = New-Object System.Collections.Generic.List[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    $queue.Enqueue($RootId)
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        if ($ids.Contains($current)) { continue }
        $ids.Add($current) | Out-Null
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$current" -ErrorAction SilentlyContinue
        foreach ($child in $children) { $queue.Enqueue([int]$child.ProcessId) }
    }
    return $ids
}

# 这个进程是不是本项目起的？
#
# 只认命令行里带没带本项目路径。不能用可执行文件路径判断：前端跑的是系统装的 node.exe，
# 后端那个 venv 里的 python.exe 也只是系统 Python 的副本，系统报告的是解析后的真实路径，
# 两个都落在项目目录外。而命令行一定带着项目路径（node 指向项目里的 next、python 带着
# venv 全路径），玩家自己开的 node / python 则不会 —— 拿它当身份证既准又不会误伤。
function Test-IsProjectProcess([int]$ProcId, [string]$Root) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcId" -ErrorAction SilentlyContinue
    if (-not $p -or -not $p.CommandLine) { return $false }
    return $p.CommandLine.IndexOf($Root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
}

# 清理占着端口、且确实属于本项目的残留进程。
# PID 文件可能没记全（上次启动中途失败）或已被删掉，这时按父子关系是找不到孤儿进程的，
# 只能从端口反查。返回被清掉的进程数。
function Clear-StuckProjectPorts([string]$Root) {
    $killed = 0
    foreach ($port in @(8000, 3000)) {
        foreach ($conn in (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
            $procId = [int]$conn.OwningProcess
            if (Test-IsProjectProcess $procId $Root) {
                try {
                    Stop-Process -Id $procId -Force -ErrorAction Stop
                    $killed++
                } catch {}
            }
        }
    }
    return $killed
}

Write-Host ""
Write-Host "  正在停止心动实验室..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $PidFile)) {
    # 没有 PID 文件不代表没在跑：文件可能被删了，或上次启动中途失败没写成。
    # 仍然按端口查一遍本项目的残留进程，否则玩家会陷入「显示没运行、端口却占着」的死角。
    if ((Clear-StuckProjectPorts $Root) -gt 0) {
        Write-Host "  已清理残留进程。" -ForegroundColor Green
    } else {
        Write-Host "  没有找到正在运行的服务。" -ForegroundColor DarkGray
    }
    Start-Sleep -Seconds 2
    exit 0
}

# 只关启动脚本记录下来的那两棵进程树，绝不按进程名批量杀——
# 用户自己开的 python / node 不该被误伤。
foreach ($line in (Get-Content -LiteralPath $PidFile)) {
    $rootId = 0
    if (-not [int]::TryParse($line.Trim(), [ref]$rootId)) { continue }
    # 先收集完整棵树再动手：边杀边遍历会丢掉还没访问到的分支。
    $tree = Get-ProcessTreeIds $rootId
    # 从叶子往根杀，避免父进程先死导致子进程被系统重新挂载而漏杀。
    [array]::Reverse($tree)
    foreach ($procId in $tree) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
    }
}

Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue

# 确认端口真的放开了，而不是嘴上说停了。
Start-Sleep -Milliseconds 800

# 还占着就再兜一次底：多半是父子关系断掉的孤儿进程（PID 文件记的那层已经先退出了）。
Clear-StuckProjectPorts $Root | Out-Null
Start-Sleep -Milliseconds 500

$stuck = @()
foreach ($port in @(8000, 3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        $stuck += $port
    }
}

if ($stuck.Count -gt 0) {
    # 走到这里说明占端口的进程不是本项目的（否则上面已经清掉了），
    # 八成是玩家自己有别的程序在用这两个端口。
    Write-Host "  [!] 端口 $($stuck -join '、') 仍被占用，但占用者不是心动实验室。" -ForegroundColor Yellow
    Write-Host "      本游戏的服务已停止。如果下次启动失败，请先关掉占用这些端口的其他程序。" -ForegroundColor DarkGray
} else {
    Write-Host "  已停止。" -ForegroundColor Green
}

Write-Host ""
Start-Sleep -Seconds 2
