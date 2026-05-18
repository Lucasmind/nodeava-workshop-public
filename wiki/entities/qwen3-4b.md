# Qwen3-4B (Default LLM)

Qwen3-4B is a 4-billion-parameter instruction-tuned language model developed by Alibaba's Qwen team, and it serves as NodeAva's default conversational brain, running entirely on the user's local machine with no cloud dependency.

## Role in NodeAva

The model handles all natural language understanding and response generation. It receives the conversation history plus a system prompt from [[orchestrator]], produces streaming token output, and returns responses that the [[orchestrator]] pipeline filters, splits into sentences, and routes to [[text-to-speech]]. Qwen3-4B is a thinking model, meaning it can emit internal reasoning inside `<think>` tags before producing its visible reply. NodeAva strips that reasoning content before display and before storing the turn in conversation history.

## Model File

The default model file is `Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf`, a 4-bit quantized GGUF stored in the `models/` directory at the repository root. The `Q4_K_M` quantization keeps VRAM usage around 4.8 GB, within the 8 GB minimum recommended for the full NodeAva stack.

## Serving

The model is served by llama.cpp using the official `ghcr.io/ggml-org/llama.cpp:server` Docker image. The service listens internally on port 8080 and is exposed to the host at port 8081. It is reachable at `http://localhost:8081/v1/` via an OpenAI-compatible API.

Key server flags set in `docker-compose.yml`:

- `--jinja --reasoning-format none` — enables Jinja templating and suppresses llama.cpp's own reasoning formatting so the raw `<think>` tags pass through for NodeAva's own filter
- `--temp 0.6 --top-k 20 --top-p 0.95 --min-p 0` — sampling parameters tuned for thinking models; temperature must not be set to 0 with this model class
- `--ctx-size 4096` — default context window, overridable via the `LLM_CTX_SIZE` environment variable

On macOS, the model is served by `llama-server` installed via Homebrew rather than Docker, using Metal GPU acceleration automatically. Ports and API paths remain identical.

## Thinking Mode and Emotion Tags

After the `<think>` block, Qwen3-4B emits the visible response prefixed with an optional emotion tag such as `[happy]` or `[neutral]`. The [[orchestrator]] parses these tags to drive avatar expression changes via [[avatar]]. The `Orchestrator.js` file buffers the first seven characters of each stream to detect whether a thinking block is present before forwarding tokens downstream.

## Verification

```bash
curl http://localhost:8081/v1/models
```

A healthy response lists the loaded model file name. See also [[llm-client]] for how the frontend streams completions from this endpoint.
