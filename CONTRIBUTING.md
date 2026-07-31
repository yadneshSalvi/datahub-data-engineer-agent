# Contributing

Thanks for improving the On-Call Data Engineer Agent. Keep every DataHub write inside the
`oncall` / `oncall_demo.` namespace, never commit `.env` or runtime data, and never tear down a
shared DataHub quickstart.

Before opening a change:

```bash
cd backend
UV_CACHE_DIR=/private/tmp/uv-cache env -u VIRTUAL_ENV uv sync
UV_CACHE_DIR=/private/tmp/uv-cache env -u VIRTUAL_ENV uv run pytest
UV_CACHE_DIR=/private/tmp/uv-cache env -u VIRTUAL_ENV uv run ruff check .

cd ../frontend
bun install --frozen-lockfile
bun run build
```

Use `npm install && npm run build` if bun is unavailable. Explain behavior changes, include tests,
and call out any live DataHub verification you performed.
