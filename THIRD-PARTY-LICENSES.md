# Third-Party Licenses

NodeAva depends on the following open-source components.

## AI Models

| Component | License | Source |
|-----------|---------|--------|
| **Qwen3-4B** (LLM) | Apache-2.0 | [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) |
| **Qwen3-4B GGUF** (quantized) | Apache-2.0 | [bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF](https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF) |
| **Kokoro-82M** (TTS model) | Apache-2.0 | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) |
| **Whisper base.en** (STT model) | MIT | [openai/whisper](https://github.com/openai/whisper) |
| **Silero VAD** (voice activity) | MIT | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) |

## Server Software

| Component | License | Source |
|-----------|---------|--------|
| **llama.cpp** | MIT | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) |
| **whisper.cpp** | MIT | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) |
| **Kokoro-FastAPI** | Apache-2.0 | [remsky/Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) |

Kokoro-FastAPI includes code derived from:
- **StyleTTS2** — MIT License — [yl4579/StyleTTS2](https://github.com/yl4579/StyleTTS2)

## Avatar Model

The included avatar is licensed **separately** from the project code (Apache-2.0). If you use NodeAva commercially, replace it with your own avatar.

| Asset | License | Source | Notes |
|-------|---------|--------|-------|
| **default-avatar.glb** | CC BY-NC-SA 4.0 | [Ready Player Me](https://readyplayer.me) / Netflix | Non-commercial only. Attribution required. |

Avatar sourced from the [TalkingHead](https://github.com/met4citizen/TalkingHead) project by [met4citizen](https://github.com/met4citizen).

## Frontend Libraries

| Component | License | Source |
|-----------|---------|--------|
| **TalkingHead** | MIT | [nickaiva/talkinghead](https://github.com/nickaiva/talkinghead) |
| **Three.js** | MIT | [mrdoob/three.js](https://github.com/mrdoob/three.js) |
| **VAD-web** | ISC | [ricky0123/vad](https://github.com/ricky0123/vad) |
| **ONNX Runtime Web** | MIT | [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) |
| **Vite** | MIT | [vitejs/vite](https://github.com/vitejs/vite) |

---

## Full License Texts

### Apache License 2.0

Applies to: Qwen3-4B, Kokoro-82M, Kokoro-FastAPI, NodeAva itself.

See the [LICENSE](LICENSE) file for the full Apache-2.0 text.

### MIT License

Applies to: llama.cpp, whisper.cpp, Whisper base.en, Silero VAD, TalkingHead, Three.js, ONNX Runtime, Vite, StyleTTS2.

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### ISC License

Applies to: VAD-web.

```
Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
```
