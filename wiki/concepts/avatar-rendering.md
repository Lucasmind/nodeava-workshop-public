# The 3D Avatar

The 3D avatar is the visible face of NodeAva: a real-time animated head rendered in the browser using Three.js and the open-source TalkingHead library, which handles skeletal animation, facial blending, lip synchronization, and eye contact behavior entirely on the client side without any cloud rendering service.

## Rendering Stack

The avatar runs inside a Three.js scene managed by `frontend/src/avatar/AvatarManager.js`. The `AvatarManager` class wraps the `TalkingHead` instance and exposes a simplified interface to the rest of the pipeline. The 3D model is a `.glb` file loaded at runtime via `head.showAvatar()`. The default model ships as `default-avatar.glb` and is licensed CC BY-NC-SA 4.0, separately from the project's Apache-2.0 code license. A custom model URL can be set in `frontend/src/app/config.js` via the `avatarUrl` field.

The renderer targets 30 frames per second (`modelFPS: 30`). Camera rotation is enabled; pan and zoom are disabled to keep the framing consistent during conversation.

## Lip Sync and Audio

NodeAva does not use TalkingHead's built-in TTS endpoint. Instead, `ttsEndpoint` is set to `null`, and audio is driven externally by calling `speakAudio()` with raw PCM data and word timestamps produced by [[text-to-speech]]. TalkingHead uses those timestamps to drive viseme blending, producing mouth shapes that match the spoken words. The PCM sample rate is configured in `config.js` and must match the rate returned by Kokoro-FastAPI.

## Behavioral Parameters

Several parameters shape how the avatar behaves during idle and speaking states:

- `avatarIdleEyeContact: 0.3` — the avatar glances at the camera 30% of the time while idle.
- `avatarSpeakingEyeContact: 0.6` — eye contact increases to 60% while speaking.
- `avatarIdleHeadMove: 0.5` and `avatarSpeakingHeadMove: 0.5` — subtle head motion is active in both states.
- Mood is set via `setMood()`, which accepts values like `happy` or `neutral`. The [[llm]] pipeline parses emotion tags from the model's output and calls this method before each spoken sentence.

## Integration with the Pipeline

The `AvatarManager` sits at the output end of the [[pipeline-orchestrator]]. When the [[text-to-speech]] stage produces a PCM buffer, the orchestrator calls `speakAudio()` on the avatar. The avatar then animates and speaks in sync. The `audioCtx` getter exposes the Web Audio context so the rest of the frontend can share a single audio graph.

The `AvatarManager` is initialized once at page load and kept alive for the session. Calling `start()` begins the Three.js render loop; `stop()` halts it.
