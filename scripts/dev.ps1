<#
.SYNOPSIS
    本地一键开发环境联动脚本：启动基础设施容器、三大后端服务进程与前端热重载开发服务器。
.DESCRIPTION
    本项目采用第一性开发循环范式：**基础设施跑在容器中，业务代码运行在宿主机上**。
    执行 `docker compose -f infra/compose.yaml` 启动 PostgreSQL、Qdrant、RabbitMQ、RustFS 与 Langfuse；
    API、Agent 运行时与 Worker 运行在宿主机的 `.venv` 环境中，直接支持 `uv run`、Ruff、Pyright、断点调试
    以及前端 Vite+ 的毫秒级 HMR 热更新。

    执行步骤：
      1. 同步环境 `uv sync --locked`；
      2. 启动容器拓扑（带 `-NoCompose` 可跳过等待）；
      3. 执行数据库迁移 `alembic upgrade head` 与对象存储初始化 `storage-init`；
      4. 启动宿主业务进程（API、Agent 运行时以及 Worker），日志分别输出至 `.probe/dev/`；
      5. 启动前端开发服务器 `vp dev`（http://localhost:5173），反向代理后端双接口；
      6. 核对各服务健康状态，输出进程 PID 表格与访问入口。

    端口复用设计：
      若目标端口已在监听，脚本会复用现有进程而不强行冲突，确保开发环境安全。

    停止方式：
      `-Stop` 参数根据记录的 PID 树安全终止脚本启动的宿主进程，保留底层容器运行。
.EXAMPLE
    ./scripts/dev.ps1                      # 启动全栈：基础容器、三大后端进程与前端
    ./scripts/dev.ps1 -NoWorker            # 纯界面联调：不启动 Worker 摄取流水线
    ./scripts/dev.ps1 -NoFrontend          # 纯后端联调：不启动前端
    ./scripts/dev.ps1 -NoCompose           # 基础容器已就绪时直接启动业务进程
    ./scripts/dev.ps1 -Stop                # 安全停止由本脚本启动的宿主进程
    ./scripts/dev.ps1 -Containers          # 容器对齐路径：启动全容器化应用环境
#>
[CmdletBinding()]
param(
    [switch] $Stop,
    [switch] $NoWorker,
    [switch] $NoFrontend,
    [switch] $NoCompose,
    [switch] $Containers,
    [int] $ApiPort = $(if ($env:API_PORT) { [int] $env:API_PORT } else { 8000 }),
    [int] $AgentPort = $(if ($env:AGENT_RUNTIME_PORT) { [int] $env:AGENT_RUNTIME_PORT } else { 8001 }),
    [int] $FrontendPort = 5173,
    [int] $StartupTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$composeFile = Join-Path $repoRoot 'infra/compose.yaml'
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
$frontendDirectory = Join-Path $repoRoot 'frontend'
$logDirectory = Join-Path $repoRoot '.probe/dev'
$pidFile = Join-Path $logDirectory 'pids.json'
$apiBaseUrl = "http://127.0.0.1:$ApiPort"
$agentBaseUrl = "http://127.0.0.1:$AgentPort"
$frontendUrl = "http://localhost:$FrontendPort"

function Write-Headline {
    param([Parameter(Mandatory)][string] $Text)
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Test-PortListening {
    param([Parameter(Mandatory)][int] $Port)
    return [bool] (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Get-ListenerProcessId {
    param([Parameter(Mandatory)][int] $Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return $listener.OwningProcess }
    return $null
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory)][string] $Uri,
        [Parameter(Mandatory)][int] $TimeoutSeconds,
        [Parameter(Mandatory)][string] $Label,
        [int[]] $AcceptStatus = @(200)
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastObservation = 'no response'
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -SkipHttpErrorCheck -TimeoutSec 5
            if ($AcceptStatus -contains [int] $response.StatusCode) {
                return [int] $response.StatusCode
            }
            $lastObservation = "HTTP $($response.StatusCode)"
        }
        catch {
            $lastObservation = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 750
    }
    throw "$Label at $Uri never answered within $TimeoutSeconds s (last: $lastObservation)"
}

function Stop-ProcessTree {
    param([Parameter(Mandatory)][int] $ProcessId, [Parameter(Mandatory)][string] $Name)
    $null = & taskkill /PID $ProcessId /T /F 2>&1
    Write-Host "    $Name (pid $ProcessId) stopped" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------- -Stop

if ($Stop) {
    if (-not (Test-Path -LiteralPath $pidFile)) {
        Write-Host "无需停止：$pidFile 不存在（本脚本仅管理自身启动的进程）" -ForegroundColor Yellow
        exit 0
    }
    $recorded = @(Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json | Where-Object { $_ })
    Write-Headline "正在停止本脚本启动的 $($recorded.Count) 个服务进程"
    foreach ($entry in $recorded) {
        $alive = Get-Process -Id $entry.Pid -ErrorAction SilentlyContinue
        if ($alive) {
            Stop-ProcessTree -ProcessId $entry.Pid -Name $entry.Name
        }
        else {
            Write-Host "    $($entry.Name) (PID $($entry.Pid)) 已经退出" -ForegroundColor DarkGray
        }
    }
    Start-Sleep -Seconds 1
    foreach ($entry in $recorded) {
        if ($entry.Port -and (Test-PortListening -Port $entry.Port)) {
            Write-Warning "端口 $($entry.Port) 仍在监听 (PID $(Get-ListenerProcessId -Port $entry.Port))"
        }
    }
    Remove-Item -LiteralPath $pidFile -Force
    Write-Host ''
    Write-Host '底层依赖容器保持运行；若需彻底销毁容器，请执行：' -ForegroundColor Yellow
    Write-Host "    docker compose -f infra/compose.yaml down"
    exit 0
}

# ---------------------------------------------------------------- -Containers

if ($Containers) {
    # The parity path needs the deployment artifacts. They do not exist yet, and this says so with the
    # exact list rather than starting something that is not there.
    $missing = @()
    foreach ($relative in 'backend/Dockerfile', 'frontend/Dockerfile') {
        if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $relative))) { $missing += $relative }
    }
    # `--profile app` is required: the application services live under that profile, so the default
    # service list does not contain them and every name would look missing.
    $services = @(docker compose -f $composeFile --profile app config --services 2>$null)
    foreach ($name in 'api', 'worker', 'agent', 'web') {
        if ($services -notcontains $name) { $missing += "infra/compose.yaml 中的 '$name' 服务" }
    }
    if ($missing.Count -gt 0) {
        Write-Host '容器化路径尚未就绪。缺失项：' -ForegroundColor Yellow
        foreach ($item in $missing) { Write-Host "    - $item" }
        Write-Host ''
        Write-Host '本地开发推荐模式：容器运行基础设施，宿主机运行业务进程（运行此脚本无需 -Containers）。' -ForegroundColor Yellow
        exit 1
    }
    Write-Headline '构建并启动全栈应用容器'
    docker compose -f $composeFile --profile app up -d --build --wait --wait-timeout $StartupTimeoutSeconds
    if ($LASTEXITCODE -ne 0) { throw "compose --profile app up 执行退出，状态码 $LASTEXITCODE" }
    Write-Host ''
    Write-Host "容器已全部就绪；前端界面访问地址: $frontendUrl" -ForegroundColor Green
    Write-Host '停止并清理容器命令: docker compose -f infra/compose.yaml --profile app down'
    exit 0
}

# ---------------------------------------------------------------- the development loop

# Connection settings must match the Compose defaults; an existing environment value wins, so the
# script can also target a differently configured topology (`infra/compose.yaml` follows the same rule).
$defaultEnvironment = [ordered]@{
    LOG_LEVEL      = 'INFO'
    DATABASE_URL    = 'postgresql+asyncpg://rag:rag_local@127.0.0.1:5432/rag'
    RABBITMQ_URL    = 'amqp://rag:rag_local@127.0.0.1:5672//'
    QDRANT_URL      = 'http://127.0.0.1:6333'
    S3_ENDPOINT_URL = 'http://127.0.0.1:9000'
    S3_ACCESS_KEY   = 'ragadmin'
    S3_SECRET_KEY   = 'rag_local_secret'
}
foreach ($name in $defaultEnvironment.Keys) {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        Set-Item -Path "Env:$name" -Value $defaultEnvironment[$name]
    }
}
Set-Item -Path 'Env:API_PORT' -Value $ApiPort
Set-Item -Path 'Env:AGENT_RUNTIME_PORT' -Value $AgentPort

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$started = [System.Collections.Generic.List[object]]::new()
$reused = [System.Collections.Generic.List[object]]::new()
$failure = $null

function Start-BackendProcess {
    param(
        [Parameter(Mandatory)][string] $Name,
        [Parameter(Mandatory)][string] $Module,
        [int] $Port
    )

    if ($Port -and (Test-PortListening -Port $Port)) {
        $owner = Get-ListenerProcessId -Port $Port
        Write-Host "    ${Name}: 端口 $Port 已被占用 (PID $owner) — 复用该服务，不纳入 -Stop 管理" -ForegroundColor DarkGray
        $reused.Add([pscustomobject]@{ Name = $Name; Pid = $owner; Port = $Port })
        return
    }
    $process = Start-Process -FilePath $python `
        -ArgumentList @('-m', $Module) `
        -WorkingDirectory $repoRoot `
        -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $logDirectory "$Name.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "$Name.err.log")
    $started.Add([pscustomobject]@{ Name = $Name; Pid = $process.Id; Port = $Port })
    Write-Host "    $Name 启动成功 (PID $($process.Id), 端口 $Port)" -ForegroundColor DarkGray
}

try {
    Write-Headline 'uv sync --locked'
    uv sync --locked
    if ($LASTEXITCODE -ne 0) { throw "uv sync --locked 执行失败，状态码 $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $python)) { throw "在 $python 未找到 Python 虚拟环境解释器" }

    if ($NoCompose) {
        Write-Headline '跳过容器启动 (-NoCompose)'
    }
    else {
        Write-Headline '启动基础设施容器 (业务进程运行在宿主机)'
        docker compose -f $composeFile up -d --wait --wait-timeout $StartupTimeoutSeconds
        if ($LASTEXITCODE -ne 0) { throw "docker compose up 执行失败，状态码 $LASTEXITCODE" }
    }

    Write-Headline '执行数据库结构迁移 (alembic upgrade head)'
    uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head 执行失败，状态码 $LASTEXITCODE" }

    Write-Headline '初始化对象存储存储桶 (storage-init)'
    $init = & uv run python -m cli storage-init 2>&1
    if ($LASTEXITCODE -ne 0) { throw "storage-init 执行失败，状态码 $LASTEXITCODE : $(($init | Out-String).Trim())" }

    Write-Headline '启动后端服务进程'
    Start-BackendProcess -Name 'api' -Module 'api.main' -Port $ApiPort
    Start-BackendProcess -Name 'agent-runtime' -Module 'agent_runtime.main' -Port $AgentPort
    if ($NoWorker) {
        Write-Host '    已跳过 Worker 启动 (-NoWorker): 上传的文档将保持排队状态' -ForegroundColor DarkGray
    }
    else {
        Start-BackendProcess -Name 'worker' -Module 'worker.main'
    }

    Write-Headline '等待 HTTP 服务端点就绪'
    Wait-ForHttp -Uri "$apiBaseUrl/health/live" -TimeoutSeconds $StartupTimeoutSeconds -Label '业务 API' | Out-Null
    Wait-ForHttp -Uri "$agentBaseUrl/health/live" -TimeoutSeconds $StartupTimeoutSeconds -Label 'Agent 运行时' | Out-Null
    foreach ($surface in @(@{ Url = $apiBaseUrl; Label = '业务 API' }, @{ Url = $agentBaseUrl; Label = 'Agent 运行时' })) {
        try {
            $status = Wait-ForHttp -Uri "$($surface.Url)/health/ready" -TimeoutSeconds 30 -Label $surface.Label -AcceptStatus @(200, 503)
            if ($status -eq 200) {
                Write-Host "    $($surface.Label) 就绪" -ForegroundColor DarkGray
            }
            else {
                Write-Warning "$($surface.Label) 返回 503: 依赖组件未完全就绪；详见 $($surface.Url)/health/ready"
            }
        }
        catch {
            Write-Warning "无法获取 $($surface.Label) 就绪状态: $($_.Exception.Message)"
        }
    }

    if ($NoFrontend) {
        Write-Headline '跳过前端启动 (-NoFrontend)'
    }
    else {
        Write-Headline '启动前端开发服务器 (vp dev)'
        if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory 'node_modules'))) {
            Write-Host '    未检测到 node_modules，正在执行 pnpm install...' -ForegroundColor DarkGray
            Push-Location $frontendDirectory
            try { pnpm install } finally { Pop-Location }
            if ($LASTEXITCODE -ne 0) { throw "pnpm install 执行失败，状态码 $LASTEXITCODE" }
        }
        $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
        if (-not $pnpm) { $pnpm = Get-Command pnpm -ErrorAction SilentlyContinue }
        if (-not $pnpm) { throw '未在 PATH 中找到 pnpm 命令；请先安装 Node 24 与 pnpm 12' }
        $frontend = Start-Process -FilePath $pnpm.Source `
            -ArgumentList @('exec', 'vp', 'dev') `
            -WorkingDirectory $frontendDirectory `
            -PassThru -NoNewWindow `
            -RedirectStandardOutput (Join-Path $logDirectory 'frontend.out.log') `
            -RedirectStandardError (Join-Path $logDirectory 'frontend.err.log')
        $started.Add([pscustomobject]@{ Name = 'frontend'; Pid = $frontend.Id; Port = $FrontendPort })
        try {
            Wait-ForHttp -Uri $frontendUrl -TimeoutSeconds 90 -Label '前端开发服务器' | Out-Null
        }
        catch {
            Write-Warning "前端开发服务器尚未就绪；可查看日志 $logDirectory/frontend.out.log"
        }
    }

    # 空列表仍需输出为有效 JSON 以便 -Stop 读取
    if ($started.Count -eq 0) {
        '[]' | Set-Content -LiteralPath $pidFile -Encoding utf8
    }
    else {
        $started | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $pidFile -Encoding utf8
    }

    Write-Host ''
    Write-Host '================ 开发运行环境栈 ================' -ForegroundColor Green
    foreach ($entry in $started) {
        $url = switch ($entry.Name) {
            'api' { $apiBaseUrl }
            'agent-runtime' { $agentBaseUrl }
            'frontend' { $frontendUrl }
            default { '' }
        }
        Write-Host ("  {0,-14} PID {1,-7} {2}" -f $entry.Name, $entry.Pid, $url)
    }
    foreach ($entry in $reused) {
        Write-Host ("  {0,-14} PID {1,-7} 已复用 (非本脚本启动)" -f $entry.Name, $entry.Pid)
    }
    Write-Host ("  运行日志       {0}" -f $logDirectory)
    if (-not $NoFrontend) {
        Write-Host ("  访问入口       {0}  (仅限 localhost，请勿使用 127.0.0.1 访问)" -f $frontendUrl)
    }
    Write-Host ("  停止进程       pwsh -NoProfile -File scripts/dev.ps1 -Stop")
    Write-Host '===================================================' -ForegroundColor Green
}
catch {
    $failure = $_
}
finally {
    if ($failure) {
        # 清理半启动状态：回滚停止本轮已启动的进程并打印异常
        Write-Host ''
        Write-Host "开发栈启动失败: $($failure.Exception.Message)" -ForegroundColor Red
        foreach ($entry in $started) {
            $alive = Get-Process -Id $entry.Pid -ErrorAction SilentlyContinue
            if ($alive) { Stop-ProcessTree -ProcessId $entry.Pid -Name $entry.Name }
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        foreach ($log in 'api.err.log', 'agent-runtime.err.log', 'worker.err.log', 'frontend.err.log') {
            $path = Join-Path $logDirectory $log
            if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -gt 0) {
                Write-Host "--- $log (末尾日志) ---" -ForegroundColor Red
                Get-Content -LiteralPath $path -Tail 30
            }
        }
    }
}

if ($failure) { exit 1 }
exit 0
