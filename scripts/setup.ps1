$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败" }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "升级 pip 失败" }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "安装 requirements.txt 失败" }
# Windows 商店应用沙箱的临时目录可能很长；在 venv 内准备构建工具并关闭
# pip build isolation，可避免 editable 安装触发 MAX_PATH 问题。
& .\.venv\Scripts\python.exe -m pip install "setuptools>=68" wheel
if ($LASTEXITCODE -ne 0) { throw "安装构建工具失败" }
New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null
$env:TEMP = Join-Path $ProjectRoot ".tmp"
$env:TMP = $env:TEMP
& .\.venv\Scripts\python.exe -m pip install --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) { throw "安装项目包失败" }

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "已从 .env.example 创建 .env；请填写真实配置。"
}

if (-not (Test-Path -LiteralPath "data\candidate_profile_input.md")) {
    Copy-Item -LiteralPath "data\candidate_profile_input.example.md" `
        -Destination "data\candidate_profile_input.md"
    Write-Host "已创建本地简历输入文件（已被 .gitignore 排除）。"
}

if (-not (Test-Path -LiteralPath "data\search_goal_input.json")) {
    Copy-Item -LiteralPath "data\search_goal_input.example.json" `
        -Destination "data\search_goal_input.json"
    Write-Host "已创建本地搜索目标文件（已被 .gitignore 排除）。"
}

& .\.venv\Scripts\python.exe -m job_workflow self-check
if ($LASTEXITCODE -ne 0) { throw "项目自检失败" }

