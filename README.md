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

The first prediction request loads the CLIP model; startup can take a moment.

## Learn more

- [Expo documentation](https://docs.expo.dev/)
- [Expo Router](https://docs.expo.dev/router/introduction/)
