# Frontend E2E testing

Meshive uses Playwright for small, deterministic frontend regression tests. The
initial suite intercepts API requests and uses synthetic responses, so it never
needs a production model library, archives, or credentials.

## Local development start

Start the backend from the existing development environment:

```sh
cd backend
uvicorn meshive.main:app --reload
```

For manual full-stack development, start the frontend in another terminal:

```sh
cd frontend
npm ci --include=dev
npm run dev
```

Vite listens on port 5173 and proxies `/api` to the backend on port 8000.
Use a temporary `MESHIVE_DATA_DIR`, cache directory, and an empty temporary
library root for manual tests. Create a test administrator through the normal
first-run flow with `MESHIVE_SETUP_TOKEN`, or with `meshive create-admin`.
Never use a production library or production account for automated tests.

## Playwright

Install the browser once after installing frontend dependencies:

```sh
cd frontend
npx playwright install chromium
npx playwright install-deps chromium
```

The second command installs Linux system libraries and may request your sudo
password. Do not prefix `npx` with `sudo`; Playwright invokes sudo itself when
needed.

Run the suite:

```sh
npm run test:e2e
```

Playwright starts the existing Vite development server automatically. For
interactive debugging, use `npm run test:e2e:ui`.
