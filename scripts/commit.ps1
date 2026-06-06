param(
    [Parameter(Mandatory = $true)]
    [string]$Message,

    [switch]$Push,

    [switch]$RunChecks,

    [string]$Remote = "origin"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:GIT_PAGER = "cat"

try {
    $utf8 = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
}
catch {
    Write-Host "WARNING: Could not switch console encoding to UTF-8." -ForegroundColor Yellow
}

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Fail {
    param([string]$Text)
    Write-Host ""
    Write-Host "ERROR: $Text" -ForegroundColor Red
    exit 1
}

$allowedMessagePattern = "^(feat|fix|refactor|docs|test|chore|style|perf|build|ci|revert)(\([a-z0-9-]+\))?: .+"
if ($Message -notmatch $allowedMessagePattern) {
    Fail "Commit message must follow Conventional Commits, for example: feat(chat): add session list"
}

$repoRoot = git rev-parse --show-toplevel
if (-not $repoRoot) {
    Fail "Current directory is not inside a Git repository."
}

Set-Location $repoRoot

$branch = git branch --show-current
if (-not $branch) {
    Fail "Cannot detect current branch."
}

if ($branch -eq "main") {
    Fail "Do not commit directly on main. Create a feature branch from dev first."
}

if ($branch -eq "dev") {
    Write-Host "WARNING: You are committing on dev. Team convention prefers feature/xxx branches." -ForegroundColor Yellow
}

Write-Step "Current branch"
Write-Host $branch

Write-Step "Working tree before staging"
git --no-pager status --short

Write-Step "Stage all changes"
git add -A

$stagedFiles = @(git diff --cached --name-only)
if ($stagedFiles.Count -eq 0) {
    Fail "No staged changes to commit."
}

$blockedFiles = @()
foreach ($file in $stagedFiles) {
    $normalized = $file -replace "\\", "/"

    if (
        $normalized -eq ".env" -or
        $normalized -like ".env.*" -or
        $normalized -like "data/*.db" -or
        $normalized -like "data/*.db-*" -or
        $normalized -like ".venv/*" -or
        $normalized -like "__pycache__/*" -or
        $normalized -like "*/__pycache__/*" -or
        $normalized -like "*.pyc" -or
        $normalized -like "*.pyo" -or
        $normalized -like ".tmp/*" -or
        $normalized -like "*.log"
    ) {
        $blockedFiles += $file
    }
}

if ($blockedFiles.Count -gt 0) {
    Write-Host ""
    Write-Host "Blocked risky files:" -ForegroundColor Red
    $blockedFiles | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    Fail "Remove these files from the commit before retrying. The script did not commit anything."
}

Write-Step "Staged files"
git --no-pager diff --cached --name-status

if ($RunChecks) {
    Write-Step "Run compile check"
    python -m compileall app.py src tests

    Write-Step "Run unittest"
    python -m unittest discover -s tests
}
else {
    Write-Step "Skip tests"
    Write-Host "Tests are skipped by default. Use -RunChecks when you want compileall and unittest."
}

Write-Step "Create commit"
git commit -m $Message

if ($Push) {
    Write-Step "Push branch"
    git push -u $Remote $branch
}

Write-Step "Final status"
git --no-pager status --short
