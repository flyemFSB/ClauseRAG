<#
.SYNOPSIS
    后端代码与黄金评测集工具链全量静态检查：依赖锁定同步、Ruff 检查、Ruff 格式化、
    Pyright 严格类型检查、主入口导入、架构单向依赖以及评测集可复现性核验。
.EXAMPLE
    ./scripts/check.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

function Invoke-Step {
    param(
        [Parameter(Mandatory)][string] $Label,
        [Parameter(Mandatory)][scriptblock] $Action
    )

    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $Label (exit code $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Invoke-Step 'uv sync --locked' { uv sync --locked --group eval }
# 同步 eval 依赖组：infrastructure/evaluation 位于 backend/src 内并引入了 ragas；
# 同步 eval 组可确保 Pyright strict 获得完整类型定义。生产部署镜像不受影响（不带 --group eval）。
Invoke-Step 'ruff check backend/src' { uv run ruff check backend/src }
Invoke-Step 'ruff format --check backend/src' { uv run ruff format --check backend/src }
Invoke-Step 'pyright backend/src' { uv run pyright backend/src }
# 静态校验四个主进程入口（api、agent_runtime、worker、cli）：
# 捕获仅在运行时装配阶段才会暴露的模块导入与依赖绑定隐患。
Invoke-Step 'entrypoint imports' {
    uv run python -c "import api.main, agent_runtime.main, worker.main, cli.main"
}
# 架构单向依赖门禁：静态扫描全部内部导入，严格禁止越层与反向依赖（api -> application -> domain）。
Invoke-Step 'check-architecture' { uv run python scripts/check-architecture.py }
# 黄金评测集脚本代码规范与类型检查。
Invoke-Step 'ruff check goldenset scripts' {
    uv run ruff check scripts/build-goldenset.py scripts/goldenset_to_ragas.py
}
Invoke-Step 'ruff format --check goldenset scripts' {
    uv run ruff format --check scripts/build-goldenset.py scripts/goldenset_to_ragas.py
}
Invoke-Step 'pyright goldenset scripts' {
    uv run pyright scripts/build-goldenset.py scripts/goldenset_to_ragas.py
}
# 黄金评测集可复现性核验：基于固定种子核验生成制品哈希指纹，杜绝评测集静默漂移。
Invoke-Step 'goldenset reproducibility' { uv run python scripts/build-goldenset.py --verify }
Invoke-Step 'goldenset RAGAS projection' { uv run python scripts/goldenset_to_ragas.py }

Write-Host 'All static checks passed.' -ForegroundColor Green
exit 0
