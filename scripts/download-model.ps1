# Download the Qwen3-4B LLM model (GGUF format) from HuggingFace
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$ModelDir = Join-Path $ProjectDir "models"
$ModelFile = "Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
$ModelPath = Join-Path $ModelDir $ModelFile
$HfRepo = "bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF"
$HfUrl = "https://huggingface.co/$HfRepo/resolve/main/$ModelFile"

if (Test-Path $ModelPath) {
    Write-Host "Model already exists: $ModelPath"
    exit 0
}

if (-not (Test-Path $ModelDir)) {
    New-Item -ItemType Directory -Path $ModelDir | Out-Null
}

Write-Host "Downloading $ModelFile (~2.5 GB)..."
Write-Host "Source: $HfRepo"

# Prefer huggingface-cli if available
$hfCli = Get-Command huggingface-cli -ErrorAction SilentlyContinue
if ($hfCli) {
    Write-Host "Using huggingface-cli..."
    & huggingface-cli download $HfRepo $ModelFile --local-dir $ModelDir --local-dir-use-symlinks False
} else {
    Write-Host "Using Invoke-WebRequest (this may take a while)..."
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $HfUrl -OutFile $ModelPath -UseBasicParsing
    $ProgressPreference = "Continue"
}

Write-Host "Model downloaded: $ModelPath"
