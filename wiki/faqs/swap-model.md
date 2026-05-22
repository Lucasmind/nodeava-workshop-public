# How do I swap the LLM model?

NodeAva's [[orchestrator]] sits at port 8082 and accepts a `model` field per request, so swapping the LLM does not require restarting any service — it can be done at the request level, the deploy level, or by pointing the local llama-server at a different file.

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
