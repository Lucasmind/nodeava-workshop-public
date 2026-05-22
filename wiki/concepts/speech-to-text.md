# Speech-to-Text (STT)

Speech-to-text is the pipeline stage that converts the user's spoken audio into a text string that NodeAva can pass to the language model. NodeAva handles this entirely on the local machine using Whisper base.en, served by whisper.cpp on port 8080, so no audio ever leaves the user's hardware.

## How It Works

The STT stage has two distinct responsibilities: detecting when the user is speaking, and transcribing what they said. These are handled by separate components that work together inside `frontend/src/stt/STTManager.js`.

Voice activity detection (VAD) runs in the browser using the `@ricky0123/vad-web` library, which loads a Silero VAD model via ONNX WebAssembly. The VAD watches the microphone stream continuously and fires events when speech starts and ends. NodeAva configures it with a `positiveSpeechThreshold` and `negativeSpeechThreshold` drawn from `frontend/src/app/config.js`, along with 8 redemption frames, a minimum of 3 speech frames, and 1 pre-speech padding frame. Short sounds that fall below the minimum frame count are discarded as misfires without triggering a transcription request.

When the VAD signals that speech has ended, `STTManager` receives the raw audio as a Float32Array sampled at 16 kHz. It converts that buffer to a WAV file using `float32ToWav` from `frontend/src/utils/audio-utils.js`, then POSTs it as multipart form data to the STT endpoint. The request specifies `model: whisper-1` and `response_format: json`. The whisper.cpp server processes the audio and returns a JSON object containing the transcribed text.

## Service and Routing

The whisper.cpp service runs on internal port 8080 and is exposed externally on port 8080 as well. In the Docker setup, nginx routes requests from the browser at `/api/stt/` to the whisper.cpp container. On macOS, the Vite dev server proxies directly to `localhost:8080` without nginx. The STT service uses Vulkan for GPU acceleration on both NVIDIA and AMD setups. The service can be tested directly with:

```
curl -X POST http://localhost:8080/v1/audio/transcriptions \
  -F "file=@test.wav" -F "model=base.en"
```

## Lazy Initialization

The VAD and microphone are initialized only when the user first activates listening, not on page load. This avoids triggering the browser's microphone permission prompt before the user has interacted with the interface. If the browser denies microphone access or no microphone is found, `STTManager` classifies the error and surfaces a human-readable message through its `onError` callback.

## Pipeline Position

STT sits at the entry point of the conversation pipeline. A successful transcription fires the `onTranscription` callback with the trimmed text string, which the [[orchestrator]] picks up and forwards to the [[large-language-model]] stage. The system state moves from `LISTENING` through `TRANSCRIBING` before handing off to `THINKING`. See [[text-to-speech]] for the output end of the same pipeline.
