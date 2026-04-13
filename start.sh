#!/usr/bin/env bash
# Start both backend and frontend development servers.
# Run from the project root: ./start.sh

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Starting Anki Maxxing"
echo ""
echo "Make sure Anki is running with AnkiConnect add-on (code: 2055492159)"
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API docs: http://localhost:8000/docs"
echo ""

# Backend
cd "$ROOT"
echo "[backend] Starting FastAPI..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Frontend
cd "$ROOT/frontend"
echo "[frontend] Starting Next.js..."
npm run dev &
FRONTEND_PID=$!

# Wait and clean up
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait $BACKEND_PID $FRONTEND_PID
