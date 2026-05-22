# System Requirements

NodeAva requires a dedicated GPU on every supported platform — there is no CPU-only mode, because real-time TTS inference is too slow without hardware acceleration.

**Linux and Windows (Docker)**

- GPU: NVIDIA or AMD with 8 GB VRAM minimum (approximately 4.8 GB is used at runtime)
- Docker Engine with Compose V2
- Disk: approximately 5 GB for models plus 10 GB for Docker images; AMD users need around 30 GB due to the ROCm image
- Windows with AMD GPU is not supported due to a Docker Desktop and WSL2 limitation

**macOS (Native, Experimental)**

- Apple Silicon only: M1, M2, M3, or M4 (Intel Macs are not supported)
- macOS 13 (Ventura) or later
- 16 GB unified memory recommended; 8 GB is the minimum
- Homebrew, Python 3.10 or later, and Node.js 18 or later
- macOS runs services natively rather than in Docker because Docker Desktop does not pass through Metal or MPS GPU access

All three AI services — [[llm]], [[text-to-speech]], and [[speech-to-text]] — must run on GPU. The VRAM breakdown is approximately 3.5 GB for the LLM, 1.0 GB for TTS, and 0.3 GB for STT. See [[gpu-support]] for vendor-specific setup details.
