# APIs, frameworks and tools

Everything BrickVisionX uses, what it is used for, and where. Versions are the ones pinned in `uv.lock` and `package-lock.json` at submission.

## AI models and external APIs

| API | Used for | How it is called | Where |
|---|---|---|---|
| **Gemini 3.8 Flash** (`gemini-3.8-flash`), Gemini Developer API | BrickBuddy: turns a request plus screen and viewer state into a spoken reply and a list of viewer actions | `google-genai` SDK, `generate_content` with a JSON response schema, thinking level `low`, one attempt per request | `apps/api/src/guide2build/chat.py` |
| **Gemini 3.8 Flash** through **Google ADK** | Reconstruction engine: proposes booklet page indexes and assembly steps as schema-constrained JSON | ADK `LlmAgent` and `Runner`, one model call per request, frozen budget per job | `apps/api/src/guide2build/engine/adk_runtime.py`, `engine/provider.py` |
| **Gradium speech-to-text** | Live transcription of the builder's speech and end-of-turn detection | WebSocket `wss://api.gradium.ai/api/speech/asr`, 24 kHz PCM in 80 ms chunks, opened from the browser with a short-lived token | `apps/web/src/gradiumVoice.ts` |
| **Gradium text-to-speech** | BrickBuddy's voice for replies and step narrations | WebSocket `wss://api.gradium.ai/api/speech/tts`, 48 kHz PCM streamed and scheduled with Web Audio | `apps/web/src/gradiumVoice.ts` |
| **Gradium token endpoint** | Short-lived tokens so the browser never holds the API key | `GET https://api.gradium.ai/api/api-keys/token` from the backend | `apps/api/src/guide2build/voice.py` |
| **LEGO building-instruction PDFs** | The only assembly evidence: the official booklet for the selected build | Downloaded at setup from the official URLs in `config/sets.json`, with a size limit and a recorded hash | `apps/api/src/guide2build/source.py`, `tools/fetch_guide.py` |
| **LDraw parts library** | Geometry for individual parts and the colour table | Individual part files fetched from `library.ldraw.org` with their notices, dependencies and hashes recorded | `tools/fetch_parts.py` |

Evaluated and not used in the app: the Antigravity managed agent and Gemini Live. The reasons are in the [technical overview](HACKATHON_TECHNICAL.md#9-options-considered-and-not-used).

## Backend (Python 3.11+)

| Library | Version | Used for |
|---|---|---|
| FastAPI | 0.141.1 | HTTP API |
| Uvicorn | 0.54.0 | ASGI server |
| Pydantic | 2.13.5 | Request, response and scene data models |
| google-genai | 2.29.0 | Gemini Developer API client |
| google-adk | 2.11.0 | Agent runtime for the reconstruction engine |
| httpx | 0.28.1 | Outbound HTTP (Gradium token, official sources) |
| pypdfium2 | 5.13.0 | Rendering booklet PDF pages |
| Pillow | 12.3.0 | Image handling for page renders |
| jsonschema | 4.26.0 | Validating scene and contract files |
| python-dotenv | 1.2.4 | Loading the local `.env` |
| SQLite (standard library) | | Local job, review and revision store |

## Frontend (Node.js 22.12+)

| Library | Version | Used for |
|---|---|---|
| React | 19.3.0 | UI |
| Three.js | 0.180.0 | 3D rendering, including its `LDrawLoader` and `OrbitControls` add-ons |
| TypeScript | 5.9.3 | Typed source, strict mode |
| Vite | 6.4.3 | Dev server and production build |
| @tabler/icons-react | 3.48.0 | Icons |
| ajv | 8.20.0 | Validating scene JSON in the browser |

Browser platform APIs used directly, without a library:

| API | Used for |
|---|---|
| WebSocket | Gradium speech streams |
| `getUserMedia`, AudioWorklet | Microphone capture off the main thread |
| Web Audio API | Gapless playback of streamed speech, the showpiece sound effects |
| Web Speech API | Fallback speech when Gradium is unavailable |
| WebGL (through Three.js) | The 3D viewer |

## Testing and quality

| Tool | Version | Used for |
|---|---|---|
| pytest | 9.1.1 | Backend tests (offline, synthetic model responses) |
| Vitest | 4.1.11 | Frontend unit tests |
| Playwright | 1.63.0 | Browser tests |
| Ruff | 0.16.10 | Python linting |
| GitHub Actions | | CI: `tools/check.py` and the Playwright "software" project on every push |

`tools/check.py` runs the linter, both test suites, the type check and a production build in one command.

## Development tools

| Tool | Used for |
|---|---|
| **Entire** (CLI 0.11.4) | Captures every coding-agent session as checkpoints tied to commits; trails for reviewable changes; multi-agent code review; `entire why` for line-level provenance |
| **Claude Code** | Coding agent for the BrickBuddy chat, voice, viewer actions, tests and these documents |
| **Codex** | Coding agent for the engine and the Google ADK migration; second reviewer in one Entire review |
| uv | Python environment and lockfile |
| npm workspaces | JavaScript dependencies |
| Git and GitHub | Source control and hosting |

## Our own HTTP API

Routes added at the hackathon:

| Route | Purpose |
|---|---|
| `POST /api/v1/chat` | One BrickBuddy turn: messages plus screen and viewer state in, reply plus checked actions out |
| `POST /api/v1/voice/token` | A short-lived Gradium token and the configured voice id |

Routes of the underlying guide (pre-existing), specified in [05_API_SPEC.md](05_API_SPEC.md):

| Route | Purpose |
|---|---|
| `GET /api/v1/health`, `GET /api/v1/config` | Status and runtime mode |
| `GET /api/v1/sets/{set_number}` | A set and its official booklets |
| `GET /api/v1/sets/{set_number}/guides/{guide_id}/scene`, `/status`, `/bom` | The 3D scene, its preparation status and bill of materials |
| `GET /api/v1/sources/{source_hash}/pages/{page_index}` | A rendered page of the official booklet |
| `POST /api/v1/conversions`, `GET /api/v1/jobs/{job_id}`, `/events`, `POST …/cancel`, `…/retry` | Booklet preparation jobs |
| `GET /api/v1/reconstructions/{revision}/scene`, `/review-items`, `POST …/corrections`, `…/review` | Revisioned scenes and the review workflow |

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | For chat and the engine | Gemini Developer API key, backend only |
| `GOOGLE_GENAI_USE_VERTEXAI` | Keep `FALSE` | Use the Gemini Developer API, not Vertex AI |
| `GRADIUM_API_KEY` | For voice | Gradium key, backend only |
| `GRADIUM_VOICE_ID` | No | Voice for BrickBuddy; defaults to "Emma" |
| `BRICKVISIONX_CHAT_MODEL` | No | Chat model override; defaults to `gemini-3.8-flash` |
| `BRICKVISIONX_CHAT_MAX_REPLIES` | No | Cap on paid chat replies per API process; defaults to 300 |
| `GUIDE2BUILD_DATA_DIR` | No | Local data folder; defaults to `var` |
| `GUIDE2BUILD_API_ORIGIN` | No | Where the dev web server proxies the API; defaults to `http://127.0.0.1:8000` |
