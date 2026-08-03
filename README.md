# Green Bin

Expo (React Native) app for scanning items and finding nearby disposal guidance, plus a Python backend for image classification.

## Mobile app (Expo)

1. Install dependencies:

   ```bash
   npm install
   ```

2. Start the dev server:

   ```bash
   npx expo start
   ```

The scanner calls the backend on **port 8000** (see `app/(tabs)/index.tsx`). Use a real device or emulator on the same network as your machine, or set `API_HOST_OVERRIDE` if the dev host is not auto-detected.
If you need to force a host manually, set `EXPO_PUBLIC_API_HOST_OVERRIDE=your-machine-ip` before starting Expo.

## Backend (Python)

From the **repository root** (`green-bin-app/`):

1. Create a virtual environment (recommended) and install deps:

   ```bash
   pip install -r backend/requirements.txt
   ```

2. Run the API:

   ```bash
   uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
   ```

   - Health: `GET http://localhost:8000/health`
   - Predict: `POST http://localhost:8000/predict` (multipart file field)

3. Add the required backend environment variables in `backend/.env`:

   ```env
   CLOUDFLARE_ACCOUNT_ID=your-cloudflare-account-id
   CLOUDFLARE_API_TOKEN=your-workers-ai-api-token
   CLOUDFLARE_AI_MODEL=@cf/meta/llama-3.2-11b-vision-instruct
   GEMINI_API_KEY=your-google-ai-studio-api-key
   GEMINI_TEXT_MODEL=gemini-3.5-flash-lite
   GEMINI_TEXT_TIMEOUT_SECONDS=20
   GEMINI_TEXT_MAX_OUTPUT_TOKENS=700
   ENABLE_LLM_GUIDANCE=true
   ENABLE_EARTH911_LLM_MATCHING=true
   ENABLE_TAVILY_LOCAL_GUIDANCE=true
   TAVILY_API_KEY=your-tavily-api-key
   TAVILY_TIMEOUT_SECONDS=10
   TAVILY_DAILY_CREDIT_LIMIT=100
   TAVILY_MONTHLY_CREDIT_LIMIT=1000
   DAILY_SCAN_LIMIT=40
   REQUIRE_SCAN_CLIENT_ID=false
   ENABLE_CLIP_WARMUP=true
   ENABLE_NEAREST_PHASH_LOOKUP=false
   SUPABASE_URL=your-supabase-project-url
   SUPABASE_KEY=your-backend-only-service-role-key
   ```

   `CLOUDFLARE_AI_MODEL` configures only the unchanged Cloudflare vision path. Text-only guidance and Earth911 catalog classification call Google AI Studio directly with `GEMINI_API_KEY`.
   `GEMINI_TEXT_MODEL` defaults to `gemini-3.5-flash-lite`, `GEMINI_TEXT_TIMEOUT_SECONDS` defaults to `20`, and `GEMINI_TEXT_MAX_OUTPUT_TOKENS` defaults to `700`.
   In `/predict`, the text flow is retrieval -> one Gemini guidance call -> local validation -> result sheet. Cache hits, clarification responses, and insufficient-evidence fallbacks make no text-model call.
   `ENABLE_TAVILY_LOCAL_GUIDANCE` defaults to `true`, but searches remain disabled unless `TAVILY_API_KEY` and the Supabase budget migration are configured.
   `TAVILY_TIMEOUT_SECONDS` defaults to `10`. Each eligible scan makes at most one basic Search request and never retries it.
   `TAVILY_DAILY_CREDIT_LIMIT` and `TAVILY_MONTHLY_CREDIT_LIMIT` default to `100` and `1000`. Reservations are fail-closed and reset at UTC day/month boundaries.
   `DAILY_SCAN_LIMIT` defaults to `40` if omitted or invalid.
   `REQUIRE_SCAN_CLIENT_ID` defaults to `false` for local development. Set it to `true` for production or closed testing so `/predict` rejects requests missing `X-GreenBin-Client-Id` before recognition work.
   `ENABLE_CLIP_WARMUP` defaults to `true`; set it to `false` to disable background CLIP initialization.
   `ENABLE_NEAREST_PHASH_LOOKUP` defaults to `false`; enable it only when approximate pHash matching is worth the full-cache scan cost.
   `SUPABASE_KEY` is used by backend Supabase repositories, including closed-testing feedback storage, and must never be included in the mobile app.

4. Apply `backend/migrations/004_tavily_search_budget.sql` before enabling Tavily local guidance. Its atomic RPC enforces the daily and monthly limits across concurrent backend instances and stores no user or request data.

5. For closed-testing feedback, apply `backend/migrations/003_closed_test_feedback.sql` in Supabase before enabling testers. The table has RLS enabled and grants access only to the service role. Review and the documented manual 90-day cleanup query are in `backend/queries/closed_test_feedback_review.sql`.

The prediction endpoint still sends uploaded images to Cloudflare Workers AI. Only text generation moved to Gemini.

## Learn more

- [Expo documentation](https://docs.expo.dev/)
- [Expo Router](https://docs.expo.dev/router/introduction/)
