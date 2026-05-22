# NodeAva Setup Script for Windows
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Write-Host "=== NodeAva Setup ===" -ForegroundColor Cyan
Write-Host ""

# 1. Validate Docker
try {
    $null = & docker compose version 2>&1
} catch {
    Write-Host "ERROR: Docker is not installed or Docker Compose V2 is not available." -ForegroundColor Red
    Write-Host "Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
    exit 1
}
Write-Host "Docker: OK"

# 2. Detect GPU
Write-Host ""
Write-Host "--- GPU Detection ---"

$GpuType = "none"
$VramMB = 0

# Check NVIDIA via nvidia-smi
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    try {
        $vramOutput = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>&1
        if ($LASTEXITCODE -eq 0) {
            $GpuType = "nvidia"
            $VramMB = [int]($vramOutput.Trim())
        }
    } catch {}
}

# Fallback: check WMI for GPU info
if ($GpuType -eq "none") {
    $gpus = Get-CimInstance Win32_VideoController 2>$null
    foreach ($gpu in $gpus) {
        $name = $gpu.Name.ToLower()
        if ($name -match "nvidia") {
            $GpuType = "nvidia"
            if ($gpu.AdapterRAM -gt 0) {
                $VramMB = [math]::Floor($gpu.AdapterRAM / 1MB)
            }
            break
        }
        if ($name -match "amd|radeon") {
            $GpuType = "amd"
            break
        }
    }
}

if ($GpuType -eq "none") {
    Write-Host "ERROR: No supported GPU detected." -ForegroundColor Red
    Write-Host "NodeAva requires an NVIDIA GPU on Windows (or NVIDIA/AMD on Linux)."
    exit 1
}

if ($GpuType -eq "amd") {
    Write-Host "ERROR: AMD GPU detected, but Docker Desktop on Windows does not support AMD GPU passthrough." -ForegroundColor Red
    Write-Host "This is a Docker/WSL2 platform limitation."
    Write-Host "Options:"
    Write-Host "  - Use Linux with AMD GPU support"
    Write-Host "  - Use an NVIDIA GPU on Windows"
    exit 1
}

Write-Host "Detected GPU: $GpuType"
if ($VramMB -gt 0) {
    $VramGB = [math]::Floor($VramMB / 1024)
    Write-Host "VRAM: ${VramMB} MB (~${VramGB} GB)"
    if ($VramMB -lt 7500) {
        Write-Host ""
        Write-Host "WARNING: Less than 8 GB VRAM detected." -ForegroundColor Yellow
        Write-Host "NodeAva needs ~4.8 GB VRAM. You may experience issues."
    }
} else {
    Write-Host "VRAM: could not detect (will check at runtime)"
}
Write-Host ""

# 3. Download LLM model
Write-Host "--- Model Download ---"
& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptDir "download-model.ps1")
Write-Host ""

# 4. Create .env
$EnvFile = Join-Path $ProjectDir ".env"
$EnvExample = Join-Path $ProjectDir ".env.example"
if (-not (Test-Path $EnvFile)) {
    Write-Host "Creating .env from .env.example..."
    $content = Get-Content $EnvExample -Raw
    $content = $content -replace "GPU_TYPE=.*", "GPU_TYPE=$GpuType"
    Set-Content -Path $EnvFile -Value $content -NoNewline
    Write-Host ".env created with GPU_TYPE=$GpuType"
} else {
    Write-Host ".env already exists (GPU_TYPE not modified)"
}
Write-Host ""

# 5. Create models directory
$ModelDir = Join-Path $ProjectDir "models"
if (-not (Test-Path $ModelDir)) {
    New-Item -ItemType Directory -Path $ModelDir | Out-Null
}

# 6. Check for avatar model
$AvatarPath = Join-Path $ProjectDir "frontend\public\avatars\default-avatar.glb"
if (-not (Test-Path $AvatarPath)) {
    Write-Host "--- Avatar Required ---" -ForegroundColor Yellow
    Write-Host "No avatar model found at: frontend\public\avatars\default-avatar.glb"
    Write-Host ""
    Write-Host "You need a GLB avatar with ARKit blend shapes and Oculus Visemes."
    Write-Host "The easiest way:"
    Write-Host "  1. Download VRoid Studio from https://vroid.com/en/studio (free)"
    Write-Host "  2. Create a character"
    Write-Host "  3. Export as VRM (TalkingHead supports VRM natively)"
    Write-Host "  4. Save as frontend\public\avatars\default-avatar.glb"
    Write-Host ""
    Write-Host "See frontend\public\avatars\README.md for more options."
    Write-Host ""
}

# 7. Print compose command
$ComposeCmd = "docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml"
Write-Host "GPU profile: NVIDIA (CUDA)"
Write-Host ""

Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To start NodeAva:"
Write-Host "  cd $ProjectDir"
Write-Host "  $ComposeCmd up --build"
Write-Host ""
Write-Host "Then open http://localhost:3000 in your browser."
