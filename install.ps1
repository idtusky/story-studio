# Story Studio Installer (Windows PowerShell)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Story Studio 故事工坊 一键安装器" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$userHome = [Environment]::GetFolderPath('UserProfile')
$targetCandidates = @(
    (Join-Path $userHome ".codex\skills"),
    (Join-Path $userHome ".claude\skills"),
    (Join-Path $userHome ".agents\skills")
)

$targetSkillsDir = $null
foreach ($dir in $targetCandidates) {
    $parentDir = Split-Path $dir
    if (Test-Path -LiteralPath $parentDir) {
        $targetSkillsDir = $dir
        break
    }
}

if (-not $targetSkillsDir) {
    $targetSkillsDir = Join-Path $userHome ".codex\skills"
}

if (-not (Test-Path -LiteralPath $targetSkillsDir)) {
    New-Item -ItemType Directory -Path $targetSkillsDir -Force | Out-Null
}

$destDir = Join-Path $targetSkillsDir "story-studio"
$srcDir = $PSScriptRoot

Write-Host "检测到 Agent 技能目录: $targetSkillsDir" -ForegroundColor Green
Write-Host "目标安装路径: $destDir"

if ($srcDir.TrimEnd('\') -ieq $destDir.TrimEnd('\')) {
    Write-Host "[OK] 当前已在目标技能目录中，无需重复复制。" -ForegroundColor Green
} else {
    Write-Host "正在复制技能文件到目标目录..." -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -Path "$srcDir\*" -Destination $destDir -Recurse -Force
    Write-Host "[OK] 技能文件安装完成！" -ForegroundColor Green
}

$bootstrapScript = Join-Path $destDir "scripts\bootstrap.ps1"
if (Test-Path -LiteralPath $bootstrapScript) {
    Write-Host ""
    Write-Host "正在运行环境依赖检查..." -ForegroundColor Cyan
    try {
        & powershell.exe -ExecutionPolicy Bypass -File $bootstrapScript -Action check
    } catch {
        Write-Host "环境检查完成，缺少的部分可在 Agent 中自动配置。" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "安装完成！" -ForegroundColor Green
Write-Host "现在你可以打开你的 AI Agent，直接发送：" -ForegroundColor White
Write-Host "  使用 `$story-studio，帮我一键配置全部运行环境。" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Green
