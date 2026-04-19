# Repository Guidelines

## Project Structure & Module Organization

This repository is a full-stack FastAPI template. Backend code lives in `backend/app`, with routes in `backend/app/api/routes`, configuration in `backend/app/core`, SQLModel models in `backend/app/models.py`, and Alembic migrations in `backend/app/alembic/versions`. Backend tests are in `backend/tests`.

Frontend code lives in `frontend/src`. Routes are in `frontend/src/routes`, reusable components in `frontend/src/components`, hooks in `frontend/src/hooks`, and generated OpenAPI client code in `frontend/src/client`. End-to-end tests are in `frontend/tests`. Static assets are in `img` and `frontend/public`.

## Build, Test, and Development Commands

- `docker compose watch`: start the full local stack with live reload.
- `bun run dev`: run the Vite frontend from the repo root.
- `cd backend && fastapi dev app/main.py`: run the backend locally after stopping the Docker backend service.
- `cd backend && bash scripts/test.sh`: run backend pytest with coverage.
- `bun run test`: run frontend Playwright tests.
- `bun run lint`: run Biome checks for the frontend.
- `cd backend && bash scripts/lint.sh`: run mypy, ty, Ruff, and format checks.
- `bash scripts/test.sh`: build the Docker stack and run backend tests in containers.

## Coding Style & Naming Conventions

Python targets 3.10+ and uses Ruff, mypy strict mode, and ty. Keep backend modules snake_case, route files grouped by resource, and tests named `test_*.py`. TypeScript uses Biome with spaces, double quotes, and minimal semicolons. React components use PascalCase filenames; hooks use `useX.ts`.

Do not edit generated files in `frontend/src/client` or `frontend/src/routeTree.gen.ts` directly. Regenerate the client with `bash scripts/generate-client.sh` after backend API changes.

## Testing Guidelines

Backend tests use pytest and coverage; place route tests in `backend/tests/api/routes` and data-layer tests in `backend/tests/crud`. Frontend tests use Playwright specs named `*.spec.ts` in `frontend/tests`. Add focused tests for API contract changes, auth behavior, migrations, and user-visible frontend flows.

## Commit & Pull Request Guidelines

Recent history uses short, imperative, emoji-prefixed summaries, often with PR numbers, for example `Pin GitHub actions by commit SHA (#2246)`. Keep commits scoped and include generated client or migration files.

Pull requests should describe the change, list validation commands run, link related issues, and include screenshots for UI changes. Note any configuration, migration, or deployment impact explicitly.

## Security & Configuration Tips

Use `.env` for local secrets and never commit real credentials. Review `SECURITY.md`, `development.md`, and `deployment.md` before changing auth, email, Traefik, or production configuration.
