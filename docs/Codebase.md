# Codebase Overview

This project is a full-stack application template with a FastAPI backend, PostgreSQL database, React TypeScript frontend, generated API client, Docker Compose development stack, and automated backend/frontend tests.

The main idea is simple: the backend owns the data model and HTTP API, FastAPI publishes an OpenAPI schema, the frontend generates a typed client from that schema, and React screens call the generated client through TanStack Query.

## Top-Level Structure

```text
backend/              FastAPI app, database models, migrations, backend tests
frontend/             React app, routes, components, generated API client, E2E tests
scripts/              Repository-level helper scripts
compose.yml           Production-like Docker Compose services
compose.override.yml  Local development overrides
development.md        Local development workflow
deployment.md         Deployment workflow
```

Important generated or tool-managed files include `frontend/src/client`, `frontend/src/routeTree.gen.ts`, Alembic migration files in `backend/app/alembic/versions`, and lock files such as `uv.lock` and `bun.lock`.

## Backend

The backend is in `backend/app`. It is a FastAPI application using SQLModel for database tables and Pydantic-style validation schemas.

### Application Entry Point

`backend/app/main.py` creates the FastAPI app. It configures:

- the project title from settings,
- OpenAPI at `/api/v1/openapi.json`,
- CORS for configured frontend origins,
- Sentry tracing outside local development,
- all API routes under the `/api/v1` prefix.

The API router is assembled in `backend/app/api/main.py`. It includes login, users, utilities, and items routes. The private test route is only enabled when `ENVIRONMENT=local`.

### Configuration

`backend/app/core/config.py` defines the `Settings` class using `pydantic-settings`. It reads environment variables from the top-level `.env` file and validates important configuration such as:

- `SECRET_KEY`,
- `FIRST_SUPERUSER`,
- PostgreSQL connection settings,
- CORS origins,
- SMTP/email settings,
- Sentry DSN,
- environment name.

For staging and production, default placeholder secrets like `changethis` raise an error. Locally, they produce warnings.

### Database and Models

`backend/app/models.py` contains both database models and request/response schemas.

Main database tables:

- `User`: stores users, hashed passwords, role flags, creation time, and related items.
- `Item`: stores user-owned items with title, description, creation time, and owner relation.

Public response models such as `UserPublic`, `UsersPublic`, `ItemPublic`, and `ItemsPublic` keep API responses separate from database-only fields like `hashed_password`.

`backend/app/core/db.py` creates the SQLModel engine from `settings.SQLALCHEMY_DATABASE_URI` and initializes the first superuser. Schema changes are handled by Alembic migrations in `backend/app/alembic/versions`.

### Authentication and Authorization

Authentication uses OAuth2 password login and JWT bearer tokens.

Key files:

- `backend/app/api/routes/login.py`: login, token testing, password recovery, password reset.
- `backend/app/core/security.py`: password hashing, JWT creation, password verification.
- `backend/app/api/deps.py`: reusable FastAPI dependencies for database sessions, current user lookup, and superuser checks.
- `backend/app/crud.py`: user creation, user updates, email lookup, authentication, and item creation helpers.

Passwords are hashed with `pwdlib`, preferring Argon2 while still supporting bcrypt verification. JWT tokens use `HS256` and the configured `SECRET_KEY`.

### API Features

The template ships with three main API areas:

- Login and password recovery: access token creation, token validation, reset emails, and password update.
- Users: signup, current user profile, password updates, account deletion, admin-only user management.
- Items: CRUD for user-owned items. Superusers can see all items; normal users only see their own.

The backend returns typed schema objects, which become the contract used by the frontend generated client.

### Email

Email helpers live in `backend/app/utils.py`. HTML templates are stored in `backend/app/email-templates/build`, with MJML source files in `backend/app/email-templates/src`.

During Docker-based local development, `compose.override.yml` configures Mailcatcher. The backend sends SMTP mail to Mailcatcher, and captured messages are available at `http://localhost:1080`.

### Backend Testing and Tooling

Backend tests are in `backend/tests`.

Useful commands:

```bash
cd backend
bash scripts/test.sh
bash scripts/lint.sh
bash scripts/format.sh
```

`scripts/test.sh` runs pytest with coverage. `scripts/lint.sh` runs mypy, ty, Ruff linting, and Ruff formatting checks.

## Frontend

The frontend is in `frontend/src`. It uses Vite, React, TypeScript, TanStack Router, TanStack Query, Tailwind CSS, shadcn-style UI components, React Hook Form, Zod, and Playwright.

### Application Entry Point

`frontend/src/main.tsx` wires together:

- the generated OpenAPI client base URL from `VITE_API_URL`,
- token injection from `localStorage`,
- a TanStack Query client,
- global API error handling for 401/403 responses,
- TanStack Router,
- theme provider,
- toast notifications.

When an API call returns 401 or 403, the app clears the access token and redirects to `/login`.

### Routing

Routes live in `frontend/src/routes`.

Important route files:

- `__root.tsx`: root route, error component, not-found component, devtools.
- `_layout.tsx`: authenticated app layout with sidebar and footer.
- `_layout/index.tsx`: dashboard/home route.
- `_layout/items.tsx`: item management page.
- `_layout/admin.tsx`: admin-only user management page.
- `_layout/settings.tsx`: user settings page.
- `login.tsx`, `signup.tsx`, `recover-password.tsx`, `reset-password.tsx`: public auth routes.

TanStack Router generates `frontend/src/routeTree.gen.ts`; do not edit it manually.

### Authentication Flow

`frontend/src/hooks/useAuth.ts` centralizes login, signup, logout, and current-user loading.

The flow is:

1. Login form submits email and password.
2. `LoginService.loginAccessToken` calls the backend token endpoint.
3. The access token is stored in `localStorage`.
4. Future generated-client calls attach that token.
5. Authenticated routes check `isLoggedIn`.
6. The current user is loaded with `UsersService.readUserMe`.

### API Client

The frontend API client is generated from the backend OpenAPI schema into `frontend/src/client`.

Regenerate it after changing backend routes, request models, response models, or validation fields:

```bash
bash scripts/generate-client.sh
```

That script imports the FastAPI app, writes `openapi.json`, runs the frontend OpenAPI generator, and then runs frontend linting.

### Components and UI

Reusable UI and feature components are organized under `frontend/src/components`.

Common areas:

- `Common`: layout helpers, data table, errors, footer, logo.
- `Admin`: add, edit, delete, and table column components for users.
- `Items`: add, edit, delete, and table column components for items.
- `UserSettings`: account details, password changes, account deletion.
- `Sidebar`: navigation and current-user controls.
- `ui`: low-level shadcn-style primitives.

Feature pages usually compose generated API services, TanStack Query, a table or form component, and toast-based error handling.

### Frontend Testing and Tooling

Frontend E2E tests are in `frontend/tests` and use Playwright.

Useful commands:

```bash
bun run dev
bun run lint
bun run test
bun run test:ui
```

The Playwright tests expect the backend stack to be available. A typical setup is:

```bash
docker compose up -d --wait backend
bunx playwright test
```

## Docker and Local Services

`compose.yml` defines the main services:

- `db`: PostgreSQL database.
- `prestart`: runs startup tasks before the backend starts.
- `backend`: FastAPI API server.
- `frontend`: production-built frontend served by Nginx.
- `adminer`: database web UI.

`compose.override.yml` changes the behavior for local development:

- exposes ports on localhost,
- runs the backend with reload,
- adds Traefik proxy for local domain routing,
- adds Mailcatcher,
- adds a Playwright container,
- syncs backend code into the backend container during `docker compose watch`.

Common local URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Adminer: `http://localhost:8080`
- Mailcatcher: `http://localhost:1080`
- Traefik dashboard: `http://localhost:8090`

Start the full stack with:

```bash
docker compose watch
```

## Typical Feature Workflow

To add a new backend-backed feature:

1. Add or update SQLModel classes in `backend/app/models.py`.
2. Create an Alembic migration and run it against the database.
3. Add CRUD helpers in `backend/app/crud.py` if the logic is reused.
4. Add FastAPI routes in `backend/app/api/routes`.
5. Include the router in `backend/app/api/main.py`.
6. Add backend tests in `backend/tests`.
7. Regenerate the frontend client with `bash scripts/generate-client.sh`.
8. Build React routes/components that call the generated service.
9. Add or update Playwright tests for user-visible flows.
10. Run backend and frontend validation commands before committing.

## Learning Roadmap

Use this order if you are new to FastAPI, Docker, and TypeScript.

### 1. Web and API Basics

Learn HTTP methods, status codes, JSON, headers, cookies versus bearer tokens, CORS, and REST-style resource design. This makes the backend routes and frontend API calls much easier to understand.

### 2. Python Foundations

Learn Python functions, classes, type hints, virtual environments, package management, and pytest basics. Then learn how `uv` installs and runs backend dependencies in this project.

### 3. FastAPI and Pydantic

Learn path operations, dependency injection, request bodies, response models, automatic OpenAPI docs, and validation. Map those ideas to `backend/app/api/routes`, `backend/app/api/deps.py`, and `backend/app/models.py`.

### 4. SQLModel, PostgreSQL, and Alembic

Learn tables, primary keys, foreign keys, relationships, sessions, selects, inserts, updates, deletes, and migrations. Practice by modifying `User` or `Item`, creating a migration, and updating tests.

### 5. Authentication and Security

Learn password hashing, JWT claims, token expiration, OAuth2 password flow, role checks, secret management, and why production secrets must not use defaults.

### 6. Docker and Docker Compose

Learn images, containers, volumes, networks, environment variables, health checks, and service dependencies. Then study `compose.yml` and `compose.override.yml` to understand how the database, backend, frontend, Mailcatcher, Adminer, and Traefik run together.

### 7. TypeScript Foundations

Learn TypeScript types, interfaces, generics, async/await, modules, and how generated types protect frontend/backend contracts.

### 8. React, Routing, and Data Fetching

Learn React components, props, state, hooks, forms, TanStack Router, and TanStack Query. Then follow the login and items pages to see how forms, API calls, cache invalidation, and redirects work.

### 9. Frontend UI and Testing

Learn Tailwind CSS, the local UI components, React Hook Form, Zod validation, and Playwright E2E testing. Start with `frontend/tests/login.spec.ts` and `frontend/tests/items.spec.ts`.

### 10. Full-Stack Changes

Practice the complete loop: change a backend model, add a route, write tests, regenerate the client, build a frontend screen, and validate it with Playwright. Once you can complete that loop confidently, you can use this template effectively for real products.
