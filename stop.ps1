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

Write-Host ""
Write-Host "  正在停止心动实验室..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "  没有找到正在运行的服务。" -ForegroundColor DarkGray
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
$stuck = @()
foreach ($port in @(8000, 3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        $stuck += $port
    }
}

if ($stuck.Count -gt 0) {
    Write-Host "  [!] 端口 $($stuck -join '、') 仍被占用。" -ForegroundColor Yellow
    Write-Host "      可能有上次残留的进程，可在任务管理器里结束 node / python 进程。" -ForegroundColor DarkGray
} else {
    Write-Host "  已停止。" -ForegroundColor Green
}

Write-Host ""
Start-Sleep -Seconds 2
