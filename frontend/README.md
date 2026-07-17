# SentinelEdge Frontend

React + TypeScript frontend for SentinelEdge home environment monitoring.

## Features

- Metrics-first main tab with filters, graph view, and telemetry tables.
- Dedicated devices tab for status control (`pending`, `active`, `blocked`), display name, and location updates.
- Polling-based live updates tuned for local/home monitoring usage.

## Prerequisites

- Node.js 20+ and npm 10+ installed locally.
- SentinelEdge backend running on:
  - `http://localhost:8000` (default), or
  - `http://localhost:8001` (fallback).

## Quick Start

1. Install dependencies:

   ```bash
   npm install
   ```

2. Configure API URL:

   ```bash
   cp .env.example .env
   ```

   Default value:

   ```env
   VITE_API_BASE_URL=http://localhost:8000/api/v1
   ```

   If backend runs on 8001, change to:

   ```env
   VITE_API_BASE_URL=http://localhost:8001/api/v1
   ```

3. Run dev server:

   ```bash
   npm run dev
   ```

4. Open the URL shown by Vite (typically `http://localhost:5173`).

## Scripts

- `npm run dev` - start local dev server
- `npm run build` - production build
- `npm run preview` - preview production build
- `npm run lint` - run ESLint
- `npm run typecheck` - run TypeScript type checks

## Troubleshooting

- **Cannot connect to API**:
  - Confirm backend is running and reachable in browser (`/health`).
  - Verify `VITE_API_BASE_URL` points to `/api/v1` on `8000` or `8001`.
- **CORS issues**:
  - Backend should allow the frontend dev origin (for example `http://localhost:5173`).
- **No device/telemetry data**:
  - Ensure your ingestion pipeline is active and devices are present in the database.
