# Frontend development

React/TypeScript provides the controls and inspector; a high-DPI Canvas draws
transcript structure, protein features and event highlights. Data comes from
the local `/api/v1` service, with lazy feature and sequence requests.

Requires Node.js 22.13+ and pnpm. From this directory:

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Keep the backend running on port 8000; Vite proxies `/api` there. For checks
and the production bundle:

```bash
pnpm test
pnpm run typecheck
pnpm run build
```

The backend serves `dist/` in normal use. View URLs and session files carry the
dataset/build identity; keep that isolation when changing state handling.
See [testing](../docs/testing.md) for browser regressions.
