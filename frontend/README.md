# Frontend

Vite + React. In development the Vite server proxies `/api` and `/health` to `http://127.0.0.1:9100`.

```bash
npm install
npm run dev
```

Production image is a static build served by nginx, which proxies `/api` to the `api` Compose service.
