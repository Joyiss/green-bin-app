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
   ENABLE_LLM_GUIDANCE=true
   GUIDANCE_LLM_PROVIDER=groq
   GUIDANCE_LLM_MODEL=llama-3.1-8b-instant
   GROQ_API_KEY=your-groq-api-key
   DAILY_SCAN_LIMIT=40
   REQUIRE_SCAN_CLIENT_ID=false
   ENABLE_CLIP_WARMUP=true
   ENABLE_NEAREST_PHASH_LOOKUP=false
   SUPABASE_URL=your-supabase-project-url
   SUPABASE_KEY=your-backend-only-service-role-key
   ```

   `CLOUDFLARE_AI_MODEL` is optional unless you want to point Green Bin at a different Workers AI model.
   `GUIDANCE_LLM_MODEL` defaults to `llama-3.1-8b-instant` if you omit it.
   `DAILY_SCAN_LIMIT` defaults to `40` if omitted or invalid.
   `REQUIRE_SCAN_CLIENT_ID` defaults to `false` for local development. Set it to `true` for production or closed testing so `/predict` rejects requests missing `X-GreenBin-Client-Id` before recognition work.
   `ENABLE_CLIP_WARMUP` defaults to `true`; set it to `false` to disable background CLIP initialization.
   `ENABLE_NEAREST_PHASH_LOOKUP` defaults to `false`; enable it only when approximate pHash matching is worth the full-cache scan cost.
   `SUPABASE_KEY` is used by backend Supabase repositories, including closed-testing feedback storage, and must never be included in the mobile app.

4. For closed-testing feedback, apply `backend/migrations/003_closed_test_feedback.sql` in Supabase before enabling testers. The table has RLS enabled and grants access only to the service role. Review and the documented manual 90-day cleanup query are in `backend/queries/closed_test_feedback_review.sql`.

The prediction endpoint sends the uploaded image to Cloudflare Workers AI, so response time depends on network availability and remote inference latency.

## Learn more

- [Expo documentation](https://docs.expo.dev/)
- [Expo Router](https://docs.expo.dev/router/introduction/)
