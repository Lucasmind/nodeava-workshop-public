# How do I swap the LLM model?

NodeAva's [[orchestrator]] sits at port 8082 and selects the model from server-side state, so swapping the LLM can be done live from the dashboard, at the deploy level, or by changing which backend you point at.

## Easiest: pick from the dashboard (LM Studio)

 When `LLM_BACKEND=lmstudio` (the docker-compose default), the orchestrator auto-discovers **every model in your LM Studio library** and lists them in the dashboard's **Brain** dropdown (loaded models first, with a green "loaded" chip). Just pick one — selecting a model and chatting JIT-loads it in LM Studio. The **LM Studio (auto)** brain always follows whatever model you currently have loaded.

This uses LM Studio's native API (`/api/v0`) and needs LM Studio running with "Serve on Local Network" enabled. Full guide: `docs/lmstudio-runbook.md`. TTS is unaffected — LM Studio cannot do text-to-speech, so [[kokoro-tts]] still handles the voice.

## Switch model per request

Pass `provider` and `model` in the request body, plus your API key in the `X-Provider-Key` header:

```bash
curl http://localhost:8082/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'X-Provider-Key: sk-ant-…' \
  -d '{
    "provider": "anthropic",
    "model": "claude-haiku-4-5-20251001",
    "messages": [{"role": "user", "content": "hi"}]
  }'
```

Any provider that LiteLLM supports works here: `openai`, `groq`, `together`, `mistral`, and others.

## Set a different default for all requests

Edit the orchestrator's environment variables before starting the service:

```bash
PROVIDER=anthropic
PROVIDER_MODEL=claude-haiku-4-5-20251001
```

Per-request `provider` and `model` fields still override these values.

## Swap the local model file

The local backend is llama.cpp running at port 8081. Stop that service, replace the model file it loads, and restart it. The orchestrator's `LLAMA_URL` env var (default `http://localhost:8081`) does not need to change. The default local model is Qwen3-4B.

See [[orchestrator]] for full environment variable reference and [[text-to-speech]] for the TTS pipeline, which is unaffected by LLM swaps.
