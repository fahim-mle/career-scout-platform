# Frontend

React + TypeScript dashboard for Career Scout.

## Tech stack

- **React 18** + **TypeScript**
- **Vite** — dev server and build tool
- **React Router v6** — client-side routing
- **Axios** — HTTP client (proxied to `/api/v1`)
- **Tailwind CSS** — utility-first styling with glassmorphism theme
- **Lucide React** — icon set

## Running with Docker (recommended)

Served as part of the full platform. The Vite dev server runs inside the container with hot reload via volume mount:

```bash
docker compose up -d frontend
```

Access at <http://localhost:5173>.

## Running locally

```bash
npm install
npm run dev
```

Requires the backend running at `http://localhost:8000`. Create a `.env` file if needed:

```bash
VITE_API_TARGET=http://localhost:8000
```

## Pages

| Route | Page |
| --- | --- |
| `/` or `/jobs` | Job board with search and filters |
| `/jobs/:id` | Job detail view |
| `/profile` | Profile management and CV upload |
| `/applications` | Application tracking |

## Project structure

```text
src/
├── api/          — axios API calls per domain
├── components/   — reusable UI components
├── hooks/        — custom React hooks (useJobs, useProfile)
├── pages/        — full-page route components
├── types/        — TypeScript interfaces
└── lib/          — utilities (cn, date formatting)
```

## Scripts

```bash
npm run dev      # start dev server
npm run build    # production build (tsc + vite)
npm run lint     # ESLint
npm run preview  # preview production build locally
```
