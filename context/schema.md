# Schema

## Env (`.env`, ignored; loaded by `guide2build.core.environment.load_local_environment`, override=False)
- GOOGLE_API_KEY, GOOGLE_GENAI_USE_VERTEXAI=FALSE, GOOGLE_CLOUD_PROJECT=projects/885170146157, GOOGLE_CLOUD_PROJECT_NUMBER=885170146157, GUIDE2BUILD_DATA_DIR=var
- GRADIUM_API_KEY (preferred) / GRADIUM (fallback)

## Gradium REST (base https://api.gradium.ai/api, header x-api-key)
- GET /usages/credits -> {remaining_credits, allocated_credits, billing_period, next_rollover_date, plan_name}
- GET /voices/?include_catalog=true&limit=100&skip=0 -> list of {uid, name, language, is_catalog, ...}
- POST /post/speech/tts JSON {text, voice_id, output_format, only_audio:true} -> audio bytes (wav = 48 kHz 16-bit mono)
- POST /post/speech/asr body=audio, Content-Type audio/wav|pcm|ogg|opus, query json_config={"language":"en"} -> NDJSON lines {type: text|end_text|error|...}

## Voice API (local FastAPI, origin-checked POST)
- POST /api/v1/voice/token -> {token, expires_at}; 401 authentication_required, 502 otherwise
- POST /api/v1/voice/reply {messages:[{role:user|assistant, text<=2000}] (1..24, last must be user)} -> {text}; 429 voice_budget_exhausted|quota_exceeded, 401, 502
- Env GUIDE2BUILD_VOICE_MAX_REPLIES (default 60 per API process)

## Local files
- var/gradium/tts-<sha12>.wav: synthesized audio
- var/gradium/{tts,stt}-<UTC stamp>-<sha12>.json: receipt {command, endpoint, input_sha256, status, code?, elapsed_seconds, output*/transcript}; never contains the key
