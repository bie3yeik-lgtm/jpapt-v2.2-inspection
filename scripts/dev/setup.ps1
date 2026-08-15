#requires -Version 7.0

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

<#
.SYNOPSIS
    Set up the Parakeet ONNX development environment on native Windows.

.DESCRIPTION
    Responsibilities:

    - Locate repository root.
    - Verify mise.
    - Trust and install mise-managed tools.
    - Create runtime/cache directories.
    - Synchronize the Python environment using uv.
    - Run scripts/dev/doctor.py.

    This script does NOT:

    - download ONNX candidates,
    - download evaluation datasets,
    - generate Hugging Face revision locks,
    - export models,
    - run evaluation.
#>

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

function Write-SetupLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host "[setup] $Message"
}

function Write-SetupWarning {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Warning "[setup] $Message"
}

function Stop-Setup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    throw "[setup] ERROR: $Message"
}

function Test-CommandExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    return $null -ne (
        Get-Command $Command -ErrorAction SilentlyContinue
    )
}

function Invoke-Mise {
    param(
        [Parameter(
            Mandatory = $true,
            ValueFromRemainingArguments = $true
        )]
        [string[]]$Arguments
    )

    & mise exec -- @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "mise exec failed: $($Arguments -join ' ')"
    }
}

# -----------------------------------------------------------------------------
# Repository root
# -----------------------------------------------------------------------------

$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path

$Root = (
    Resolve-Path (
        Join-Path $ScriptDirectory "..\.."
    )
).Path

Set-Location $Root

$env:PARAKEET_ONNX_REPO_ROOT = $Root

Write-SetupLog "Repository root: $Root"
Write-SetupLog "Platform: windows"

# -----------------------------------------------------------------------------
# Repository sanity checks
# -----------------------------------------------------------------------------

$RequiredRepositoryPaths = @(
    "pyproject.toml",
    "mise.toml",
    "config",
    "evaluation",
    "python\src\parakeet_onnx"
)

foreach ($RelativePath in $RequiredRepositoryPaths) {
    $Path = Join-Path $Root $RelativePath

    if (-not (Test-Path $Path)) {
        Stop-Setup "Required repository path was not found: $RelativePath"
    }
}

# -----------------------------------------------------------------------------
# mise
# -----------------------------------------------------------------------------

if (-not (Test-CommandExists "mise")) {
    Stop-Setup @"
mise is required but was not found in PATH.
Install mise first, then rerun scripts/dev/setup.ps1.
"@
}

$MiseVersion = (& mise --version)

if ($LASTEXITCODE -ne 0) {
    Stop-Setup "Unable to execute mise."
}

Write-SetupLog "mise: $MiseVersion"

Write-SetupLog "Trusting repository mise configuration..."

& mise trust (Join-Path $Root "mise.toml")

if ($LASTEXITCODE -ne 0) {
    Stop-Setup "mise trust failed."
}

Write-SetupLog "Installing mise-managed tools..."

& mise install

if ($LASTEXITCODE -ne 0) {
    Stop-Setup "mise install failed."
}

# -----------------------------------------------------------------------------
# Required tools
# -----------------------------------------------------------------------------

$RequiredTools = @(
    "python",
    "uv",
    "rustc",
    "cargo"
)

foreach ($Tool in $RequiredTools) {
    & mise exec -- $Tool --version *> $null

    if ($LASTEXITCODE -ne 0) {
        Stop-Setup "mise tool is unavailable after mise install: $Tool"
    }
}

$PythonVersion = (& mise exec -- python --version 2>&1)
$UvVersion = (& mise exec -- uv --version 2>&1)
$RustVersion = (& mise exec -- rustc --version 2>&1)
$CargoVersion = (& mise exec -- cargo --version 2>&1)

Write-SetupLog "Python: $PythonVersion"
Write-SetupLog "uv: $UvVersion"
Write-SetupLog "Rust: $RustVersion"
Write-SetupLog "Cargo: $CargoVersion"

# -----------------------------------------------------------------------------
# Runtime/cache directories
# -----------------------------------------------------------------------------

$Directories = @(
    ".cache",
    ".cache\models",
    ".cache\evaluation",
    ".cache\evaluation\audio",
    ".cache\huggingface",
    ".cache\uv",
    ".ci",
    ".ci\hf\config\revisions",
    ".ci\candidate",
    ".ci\reference",
    "results",
    "tmp"
)

Write-SetupLog "Creating runtime/cache directories..."

foreach ($RelativeDirectory in $Directories) {
    $Directory = Join-Path $Root $RelativeDirectory

    New-Item `
        -ItemType Directory `
        -Force `
        -Path $Directory `
        | Out-Null
}

# -----------------------------------------------------------------------------
# Cache environment
# -----------------------------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($env:HF_HOME)) {
    $env:HF_HOME = Join-Path $Root ".cache\huggingface"
}

if ([string]::IsNullOrWhiteSpace($env:UV_CACHE_DIR)) {
    $env:UV_CACHE_DIR = Join-Path $Root ".cache\uv"
}

Write-SetupLog "HF_HOME=$($env:HF_HOME)"
Write-SetupLog "UV_CACHE_DIR=$($env:UV_CACHE_DIR)"

# -----------------------------------------------------------------------------
# Python environment
# -----------------------------------------------------------------------------

Write-SetupLog "Synchronizing Python environment with uv..."

& mise exec -- uv sync --locked

if ($LASTEXITCODE -ne 0) {
    Stop-Setup "uv sync failed."
}

# -----------------------------------------------------------------------------
# Project import
# -----------------------------------------------------------------------------

Write-SetupLog "Verifying project Python package..."

$ImportCommand = @'
import parakeet_onnx
print("[setup] Imported parakeet_onnx from:", parakeet_onnx.__file__)
'@

& mise exec -- uv run python -c $ImportCommand

if ($LASTEXITCODE -ne 0) {
    Stop-Setup "Unable to import parakeet_onnx."
}

# -----------------------------------------------------------------------------
# Doctor
# -----------------------------------------------------------------------------

Write-SetupLog "Running development environment diagnostics..."

& mise exec -- uv run python (
    Join-Path $Root "scripts\dev\doctor.py"
)

if ($LASTEXITCODE -ne 0) {
    Stop-Setup "Development environment diagnostics failed."
}

# -----------------------------------------------------------------------------
# Completion
# -----------------------------------------------------------------------------

Write-Host ""
Write-Host "Development environment setup completed."
Write-Host ""
Write-Host "Repository:"
Write-Host "  $Root"
Write-Host ""
Write-Host "Important runtime directories:"
Write-Host "  .cache\huggingface"
Write-Host "  .cache\models"
Write-Host "  .cache\evaluation"
Write-Host "  .cache\evaluation\audio"
Write-Host "  .ci\"
Write-Host "  results\"
Write-Host "  tmp\"
Write-Host ""
Write-Host "Canonical materialized-audio cache:"
Write-Host "  $(Join-Path $Root '.cache\evaluation\audio')"
Write-Host ""
Write-Host "Next diagnostic command:"
Write-Host "  mise exec -- uv run python scripts/dev/doctor.py"
Write-Host ""
