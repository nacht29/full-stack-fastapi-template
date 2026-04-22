# Repository Guidelines

## Project Structure & Module Organization

This repository is a full-stack FastAPI template. Backend code lives in `backend/app`, with routes in `backend/app/api/routes`, configuration in `backend/app/core`, SQLModel models in `backend/app/models.py`, and Alembic migrations in `backend/app/alembic/versions`. Backend tests are in `backend/tests`.

Frontend code lives in `frontend/src`. Routes are in `frontend/src/routes`, reusable components in `frontend/src/components`, hooks in `frontend/src/hooks`, and generated OpenAPI client code in `frontend/src/client`. End-to-end tests are in `frontend/tests`. Static assets are in `img` and `frontend/public`.

## Build, Test, and Development Commands

- `docker compose watch`: start the full local stack with live reload, including MySQL, backend, frontend, Mailcatcher, Adminer, and the local Traefik proxy.
- `docker compose up -d`: start the local Docker stack without watch mode.
- `docker compose down -v --remove-orphans`: stop the stack and remove volumes when a clean MySQL database is needed.
- `bun run dev`: run the Vite frontend from the repo root via the frontend workspace.
- `cd frontend && bun run build`: type-check and build the frontend.
- `bun run lint`: run Biome checks for the frontend.
- `bun run test`: run frontend Playwright tests.
- `cd backend && uv sync`: install backend Python dependencies.
- `cd backend && uv run fastapi dev app/main.py`: run the backend locally after stopping the Docker backend service or pointing it at a reachable MySQL instance.
- `cd backend && bash scripts/test.sh`: run backend pytest with coverage in the current backend environment.
- `cd backend && bash scripts/lint.sh`: run mypy, ty, Ruff, and format checks.
- `cd backend && bash scripts/format.sh`: apply Ruff fixes and formatting for backend code.
- `docker compose exec backend bash scripts/tests-start.sh`: run backend tests inside an already-running backend container.
- `bash scripts/test.sh`: build the Docker stack, run backend tests in containers, then tear the stack down.
- `bash scripts/generate-client.sh`: regenerate the frontend OpenAPI client after backend API changes, then run frontend linting.

## Coding Style & Naming Conventions

Python targets 3.10+ and uses Ruff, mypy strict mode, and ty. Keep backend modules snake_case, route files grouped by resource, and tests named `test_*.py`. TypeScript uses Biome with spaces, double quotes, and minimal semicolons. React components use PascalCase filenames; hooks use `useX.ts`.

Do not edit generated files in `frontend/src/client` or `frontend/src/routeTree.gen.ts` directly. Regenerate the client with `bash scripts/generate-client.sh` after backend API changes.

## Testing Guidelines

Backend tests use pytest and coverage; place route tests in `backend/tests/api/routes` and data-layer tests in `backend/tests/crud`. Frontend tests use Playwright specs named `*.spec.ts` in `frontend/tests`. Add focused tests for API contract changes, auth behavior, migrations, and user-visible frontend flows.

## Database & Migrations

The application uses MySQL, not PostgreSQL. The Docker database service runs `mysql:8.4`, stores data in the `app-mysql-data` volume, and is configured with `MYSQL_SERVER`, `MYSQL_PORT`, `MYSQL_DB`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_ROOT_PASSWORD`. The backend builds a `mysql+pymysql` SQLAlchemy URL from these values in `backend/app/core/config.py`.

In Docker Compose, backend and prestart containers connect to MySQL at `MYSQL_SERVER=db` on container port `3306`. For local host access, `compose.override.yml` publishes MySQL as `${MYSQL_HOST_PORT:-3307}:3306`; use port `3307` unless `MYSQL_HOST_PORT` is overridden. Adminer is available locally at `http://localhost:8080`.

Schema changes should be made through SQLModel updates in `backend/app/models.py` plus Alembic migrations in `backend/app/alembic/versions`. The `prestart` service runs `alembic upgrade head` before the backend starts and then creates the first superuser if needed. Do not switch database variables to Postgres-style names or assume SQLite-only behavior in tests.

## Commit & Pull Request Guidelines

Recent history uses short, imperative, emoji-prefixed summaries, often with PR numbers, for example `Pin GitHub actions by commit SHA (#2246)`. Keep commits scoped and include generated client or migration files.

Pull requests should describe the change, list validation commands run, link related issues, and include screenshots for UI changes. Note any configuration, migration, or deployment impact explicitly.

## Security & Configuration Tips

Use `.env` for local secrets and never commit real credentials. Change placeholder values such as `SECRET_KEY`, `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, and `FIRST_SUPERUSER_PASSWORD` before staging or production deployments. Review `SECURITY.md`, `development.md`, and `deployment.md` before changing auth, email, Traefik, database, or production configuration.
