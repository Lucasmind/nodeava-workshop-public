# TalkingHead (Avatar Engine)

TalkingHead is an open-source JavaScript library by Met4Citizen that renders a real-time 3D talking avatar in the browser using Three.js, handling lip sync, facial expressions, eye contact, head movement, and audio playback in a single integrated engine. In NodeAva, TalkingHead is the visual and audio output layer: it receives PCM audio and word timestamps from the [[text-to-speech]] pipeline and animates the avatar's face and body in sync with speech.

## Role in NodeAva

TalkingHead is instantiated and managed by `frontend/src/avatar/AvatarManager.js`. The `AvatarManager` class wraps TalkingHead and exposes a simplified interface to the rest of the frontend. The avatar model is loaded from a `.glb` file (default: the bundled `default-avatar.glb`, licensed CC BY-NC-SA 4.0) via `head.showAvatar()`. Once loaded, the [[orchestrator]] drives the avatar by calling `speakAudio()` with PCM data and subtitle callbacks produced by [[text-to-speech]].

TalkingHead's built-in TTS endpoint is disabled in NodeAva (`ttsEndpoint: null`) because audio is generated externally by [[text-to-speech]] (Kokoro-FastAPI) and fed directly as raw PCM.

## Configuration

The following options are set at initialization in `AvatarManager.js`:

- `lipsyncModules: ['en']` — English phoneme-to-viseme mapping loaded at startup
- `pcmSampleRate` — matched to the sample rate configured in `frontend/src/app/config.js`
- `modelFPS: 30` — animation frame rate
- `avatarIdleEyeContact: 0.3`, `avatarSpeakingEyeContact: 0.6` — eye contact probability during idle and speech
- `avatarIdleHeadMove: 0.5`, `avatarSpeakingHeadMove: 0.5` — head motion intensity
- Camera rotation is enabled; pan and zoom are disabled

Mood is set via `head.setMood()`, driven by emotion tags (`[happy]`, `[neutral]`, etc.) parsed from LLM output by the [[orchestrator]].

## Vite Compatibility Note

TalkingHead uses dynamic Web Workers internally and must be excluded from Vite's `optimizeDeps`. Changing this setting without clearing `node_modules/.vite` will break the avatar. See the development guide for details.

## Location in Repo

- Wrapper: `frontend/src/avatar/AvatarManager.js`
- npm package: `@met4citizen/talkinghead`
- Upstream: https://github.com/met4citizen/TalkingHead

## Related Pages

- [[orchestrator]] — drives `speakAudio()` calls
- [[text-to-speech]] — produces the PCM and word timestamps TalkingHead consumes
- [[avatar-manager]] — the NodeAva wrapper class around TalkingHead
