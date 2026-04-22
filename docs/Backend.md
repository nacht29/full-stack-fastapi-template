# Backend Architecture

This document explains how the backend in this repository is structured, how a request moves through the application, and where to make changes when adding backend features.

The backend is a FastAPI application located in `backend/app`. It uses SQLModel on top of SQLAlchemy for database models and sessions, Alembic for migrations, Pydantic settings for configuration, JWT bearer tokens for authentication, and MySQL as the default database.

## High-Level Shape

```text
backend/
  app/
    main.py                 FastAPI app factory-style entry point
    api/
      main.py               API router aggregator
      deps.py               Shared FastAPI dependencies
      routes/               Route modules grouped by feature
    core/
      config.py             Environment-driven settings
      db.py                 Database engine and initial data helper
      security.py           Password hashing and JWT helpers
    models.py               SQLModel tables plus request/response schemas
    crud.py                 Reusable data-access operations
    utils.py                Email rendering, email sending, reset-token helpers
    alembic/                Migration environment and versions
    email-templates/        Built HTML email templates and MJML source
    backend_pre_start.py    Database readiness check
    initial_data.py         First-superuser initialization
  tests/                    Pytest suite
  scripts/                  Backend helper scripts
```

The architecture is intentionally compact. There is no heavy service layer by default. Route modules contain most feature orchestration, `crud.py` holds operations reused across routes or tests, `models.py` defines both persistence and API schemas, and `deps.py` centralizes request-scoped dependencies such as database sessions and current-user lookup.

## Runtime Entry Point

`backend/app/main.py` creates the application object imported by the FastAPI CLI, tests, Docker, and the OpenAPI generation script.

It is responsible for:

- creating the `FastAPI` instance,
- setting the application title from `settings.PROJECT_NAME`,
- exposing OpenAPI at `/api/v1/openapi.json`,
- generating stable operation IDs for the frontend client,
- enabling Sentry outside local development when `SENTRY_DSN` is configured,
- registering CORS middleware for configured frontend origins,
- mounting all API routes under `settings.API_V1_STR`, which defaults to `/api/v1`.

The route operation ID function returns values like `items-read_items` and `users-create_user`. These IDs matter because the frontend OpenAPI generator uses them to produce client method names.

```text
app.main.app
  -> CORS middleware, if configured
  -> api_router mounted at /api/v1
```

## API Router Composition

`backend/app/api/main.py` builds a single `APIRouter` and includes feature routers:

- `login.router`
- `users.router`
- `utils.router`
- `items.router`
- `private.router`, only when `ENVIRONMENT == "local"`

This keeps `main.py` focused on application-level concerns and keeps each route module focused on a functional area.

The effective route groups are:

```text
/api/v1/login/access-token
/api/v1/login/test-token
/api/v1/password-recovery/{email}
/api/v1/reset-password/
/api/v1/password-recovery-html-content/{email}

/api/v1/users/
/api/v1/users/me
/api/v1/users/me/password
/api/v1/users/signup
/api/v1/users/{user_id}

/api/v1/items/
/api/v1/items/{id}

/api/v1/utils/test-email/
/api/v1/utils/health-check/

/api/v1/private/users/        local environment only
```

## Request Flow

A typical authenticated request follows this path:

```text
HTTP request
  -> FastAPI app in app/main.py
  -> /api/v1 router from app/api/main.py
  -> feature router in app/api/routes/*.py
  -> dependency resolution in app/api/deps.py
  -> SQLModel Session from app/core/db.py
  -> route logic and optional crud.py helper
  -> SQLModel/Pydantic response model serialization
  -> JSON response
```

For example, `GET /api/v1/items/` does the following:

1. FastAPI matches the request to `read_items` in `api/routes/items.py`.
2. The `session: SessionDep` dependency opens a SQLModel session.
3. The `current_user: CurrentUser` dependency validates the bearer token and loads the user.
4. The route chooses a query based on authorization:
   - superusers can list all items,
   - normal users can list only their own items.
5. The route returns `ItemsPublic`, a response schema that contains `data` and `count`.

## Configuration

Configuration lives in `backend/app/core/config.py`.

The `Settings` class extends `pydantic_settings.BaseSettings` and reads environment variables from the top-level `.env` file using:

```python
SettingsConfigDict(env_file="../.env", env_ignore_empty=True, extra="ignore")
```

Important settings include:

- `API_V1_STR`: API prefix, defaulting to `/api/v1`.
- `SECRET_KEY`: signing key for JWTs and password-reset tokens.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: access-token lifetime.
- `FRONTEND_HOST`: frontend URL used for CORS and reset-password links.
- `ENVIRONMENT`: one of `local`, `staging`, or `production`.
- `BACKEND_CORS_ORIGINS`: additional allowed browser origins.
- `PROJECT_NAME`: displayed in API metadata and emails.
- `SENTRY_DSN`: optional Sentry integration.
- `MYSQL_*`: database connection settings.
- `SMTP_*` and `EMAILS_*`: email delivery settings.
- `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD`: initial admin account.

Two computed settings are especially important:

- `all_cors_origins`: combines `BACKEND_CORS_ORIGINS` with `FRONTEND_HOST`.
- `SQLALCHEMY_DATABASE_URI`: builds the MySQL SQLAlchemy URL using the configured database values.

Security-sensitive defaults are checked by `_enforce_non_default_secrets`. If values such as `SECRET_KEY` or `FIRST_SUPERUSER_PASSWORD` are still set to `changethis`, local development receives warnings, while staging and production raise errors.

## Database Layer

The database setup is split across `core/db.py`, `models.py`, Alembic, and route or CRUD functions.

### Engine and Sessions

`backend/app/core/db.py` creates a SQLAlchemy engine through SQLModel:

```python
engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
```

Request-scoped sessions are created in `backend/app/api/deps.py`:

```python
def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
```

Routes depend on the alias:

```python
SessionDep = Annotated[Session, Depends(get_db)]
```

That means each request gets a session from the shared engine, and the session is closed after the request finishes.

### SQLModel Models

`backend/app/models.py` contains both database tables and API schemas. This is common in small SQLModel applications because SQLModel classes can serve as Pydantic validation models and SQLAlchemy ORM models.

The database tables are:

- `User`
- `Item`

`User` fields:

- `id`: UUID primary key.
- `email`: unique indexed email.
- `hashed_password`: stored password hash.
- `is_active`: account status flag.
- `is_superuser`: authorization role flag.
- `full_name`: optional display name.
- `created_at`: timezone-aware creation timestamp.
- `items`: relationship to owned `Item` rows.

`Item` fields:

- `id`: UUID primary key.
- `title`: required title.
- `description`: optional description.
- `created_at`: timezone-aware creation timestamp.
- `owner_id`: foreign key to `user.id`.
- `owner`: relationship back to `User`.

The `User.items` relationship uses cascade delete, and the `Item.owner_id` foreign key also has `ondelete="CASCADE"`. The routes still explicitly delete user-owned items before deleting a user, which keeps behavior obvious at the route level.

### Schema Classes

The same file defines request and response schemas. The main pattern is:

- `Base` classes contain shared fields.
- `Create` classes describe creation payloads.
- `Update` classes describe update payloads.
- `Public` classes describe fields returned to clients.
- Collection wrappers return `data` plus `count`.

Examples:

```text
UserBase
  -> UserCreate
  -> UserUpdate
  -> User
  -> UserPublic
  -> UsersPublic

ItemBase
  -> ItemCreate
  -> ItemUpdate
  -> Item
  -> ItemPublic
  -> ItemsPublic
```

The public schemas intentionally exclude database-only fields such as `hashed_password`.

### Migrations

Alembic is configured in:

```text
backend/alembic.ini
backend/app/alembic/env.py
backend/app/alembic/versions/
```

`env.py` imports `SQLModel.metadata` from `app.models` and sets:

```python
target_metadata = SQLModel.metadata
```

That allows Alembic autogeneration to compare the current SQLModel table definitions with the database schema.

The prestart script runs migrations automatically:

```text
backend/scripts/prestart.sh
  -> python app/backend_pre_start.py
  -> alembic upgrade head
  -> python app/initial_data.py
```

When changing database tables, update `models.py`, create a migration with Alembic, inspect the generated migration, and commit it with the code change.

## CRUD and Data Access

`backend/app/crud.py` holds reusable database operations. It is intentionally small and currently includes:

- `create_user`
- `update_user`
- `get_user_by_email`
- `authenticate`
- `create_item`

Routes can query directly with SQLModel when the operation is specific to that route. Shared behavior, security-sensitive logic, or logic used by tests belongs in `crud.py`.

Examples of logic that belongs in `crud.py`:

- password hashing during user creation,
- password hash upgrades during login,
- email lookup shared by auth and user management,
- reusable creation helpers for tests and routes.

Examples of logic currently kept in route modules:

- permission checks for a specific endpoint,
- pagination queries for a specific list endpoint,
- response-specific shape such as `UsersPublic(data=..., count=...)`.

## Authentication

Authentication is JWT-based and uses the OAuth2 password flow expected by FastAPI's tooling.

The main files are:

- `api/routes/login.py`: login and password recovery endpoints.
- `api/deps.py`: current-user and superuser dependencies.
- `core/security.py`: JWT and password helpers.
- `crud.py`: credential verification.

### Login Flow

`POST /api/v1/login/access-token` accepts an OAuth2 password form:

- `username`: the user's email.
- `password`: the user's password.

The route calls `crud.authenticate`, which:

1. Looks up the user by email.
2. Verifies the password using `verify_password`.
3. Runs a dummy password verification when the email is missing to reduce timing differences between existing and non-existing users.
4. Updates the stored password hash if the password library says the hash should be upgraded.

If authentication succeeds, the route creates a JWT access token:

```text
subject: user.id
expires: now + ACCESS_TOKEN_EXPIRE_MINUTES
algorithm: HS256
secret: SECRET_KEY
```

The response model is `Token`:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

### Current User Dependency

Protected routes use:

```python
current_user: CurrentUser
```

`CurrentUser` is an alias for `Depends(get_current_user)`.

`get_current_user`:

1. Extracts the bearer token with `OAuth2PasswordBearer`.
2. Decodes the JWT using `SECRET_KEY` and `HS256`.
3. Validates the payload as `TokenPayload`.
4. Loads the user by `sub`, which is the user ID.
5. Rejects missing or inactive users.

Routes that require admin privileges use:

```python
Depends(get_current_active_superuser)
```

That dependency checks `current_user.is_superuser`.

### Password Hashing

`core/security.py` configures `pwdlib.PasswordHash` with:

- Argon2 hashing,
- bcrypt verification support.

New passwords are hashed through `get_password_hash`. Existing hashes are verified through `verify_password`, which can return an updated hash when the stored password should be migrated to the preferred algorithm or parameters.

## Authorization Model

The authorization model is deliberately simple:

- unauthenticated users can access login, signup, password recovery, reset password, and health check endpoints,
- authenticated users can access their own profile and own items,
- superusers can manage users and see all items,
- some utility endpoints are superuser-only,
- private routes are enabled only in local development.

Authorization is enforced directly in dependencies or route functions.

Common patterns:

```python
dependencies=[Depends(get_current_active_superuser)]
```

for route-level superuser protection, and:

```python
if not current_user.is_superuser and item.owner_id != current_user.id:
    raise HTTPException(status_code=403, detail="Not enough permissions")
```

for owner-or-admin access checks.

## Route Modules

### Login Routes

`backend/app/api/routes/login.py` owns:

- access-token creation,
- token testing,
- password recovery request,
- password reset,
- password recovery email HTML preview for superusers.

Password recovery uses a separate JWT where `sub` is the user's email, `exp` is based on `EMAIL_RESET_TOKEN_EXPIRE_HOURS`, and `nbf` is set to the token creation time.

The password recovery endpoint always returns the same message whether the email exists or not. That avoids disclosing registered email addresses.

### User Routes

`backend/app/api/routes/users.py` owns:

- admin user listing,
- admin user creation,
- current-user profile update,
- current-user password update,
- current-user lookup,
- current-user deletion,
- public signup,
- lookup by user ID,
- admin user update,
- admin user deletion.

Notable behavior:

- `GET /users/` is superuser-only and supports `skip` and `limit`.
- `PATCH /users/me` prevents changing email to an email already owned by another account.
- `PATCH /users/me/password` requires the current password and rejects reusing it as the new password.
- superusers cannot delete themselves through `DELETE /users/me` or `DELETE /users/{user_id}`.
- public signup creates a normal user, not a superuser.

### Item Routes

`backend/app/api/routes/items.py` owns item CRUD.

Notable behavior:

- all item routes require authentication,
- superusers can list, read, update, and delete any item,
- normal users can only operate on items where `owner_id == current_user.id`,
- list responses are paginated with `skip` and `limit`,
- list responses return both `data` and `count`.

### Utility Routes

`backend/app/api/routes/utils.py` owns:

- `POST /utils/test-email/`: superuser-only email test endpoint.
- `GET /utils/health-check/`: unauthenticated health check returning `true`.

The Docker backend health check calls:

```text
http://localhost:8000/api/v1/utils/health-check/
```

### Private Local Routes

`backend/app/api/routes/private.py` is included only when `ENVIRONMENT == "local"`.

It currently exposes a helper endpoint to create users for local testing. Because the router is gated by environment, it is not part of staging or production when the environment is configured correctly.

## Email Architecture

Email helpers live in `backend/app/utils.py`.

The main pieces are:

- `EmailData`: small dataclass containing `html_content` and `subject`.
- `render_email_template`: loads a built HTML template and renders it with Jinja2.
- `send_email`: sends SMTP mail using the `emails` package.
- `generate_test_email`: builds test-email content.
- `generate_reset_password_email`: builds password-reset email content.
- `generate_new_account_email`: builds new-account email content.
- `generate_password_reset_token`: creates password-reset JWTs.
- `verify_password_reset_token`: decodes password-reset JWTs.

Templates are stored in:

```text
backend/app/email-templates/src/     MJML source
backend/app/email-templates/build/   HTML used at runtime
```

The app only considers email enabled when both `SMTP_HOST` and `EMAILS_FROM_EMAIL` are configured. `send_email` asserts that email configuration is present, so callers should either check `settings.emails_enabled` before sending or be routes intended to fail loudly when email is not configured.

## Startup and Initialization

In Docker, the backend service depends on a `prestart` service.

The startup sequence is:

```text
db service
  -> MySQL health check passes
  -> prestart service runs backend/scripts/prestart.sh
     -> app/backend_pre_start.py waits until SQL queries succeed
     -> alembic upgrade head applies migrations
     -> app/initial_data.py creates first superuser when missing
  -> backend service starts
```

`backend_pre_start.py` uses Tenacity to retry database access for up to five minutes.

`initial_data.py` calls `init_db`, which checks whether `settings.FIRST_SUPERUSER` already exists. If not, it creates that user with `is_superuser=True`.

## Docker and Deployment Shape

The backend is built from `backend/Dockerfile` and configured through `compose.yml`.

Important runtime services:

- `db`: MySQL 8.4 database.
- `prestart`: runs database readiness checks, migrations, and initial data.
- `backend`: runs the FastAPI application.
- `adminer`: optional database UI.
- `frontend`: production frontend served separately.

The backend container receives environment variables from `.env` and from explicit Compose environment entries. In Compose, `MYSQL_SERVER` is set to `db`, so the backend connects to the database service by Docker service name.

The backend service has a health check against `/api/v1/utils/health-check/`.

In local development, `compose.override.yml` changes the backend command to use reload behavior and syncs source code into the container for faster iteration.

## OpenAPI and Frontend Contract

FastAPI generates OpenAPI from:

- route paths,
- HTTP methods,
- request models,
- response models,
- dependency metadata,
- validation constraints.

The schema is exposed at:

```text
/api/v1/openapi.json
```

The repository-level script `scripts/generate-client.sh` imports `app.main`, writes the OpenAPI schema, and regenerates the frontend client:

```text
cd backend
uv run python -c "import app.main; import json; print(json.dumps(app.main.app.openapi()))" > ../openapi.json
cd ..
mv openapi.json frontend/
bun run --filter frontend generate-client
bun run lint
```

Any backend change that affects routes, request schemas, response schemas, validation, or operation IDs should be followed by client regeneration.

Do not edit `frontend/src/client` manually. It is generated from the backend API contract.

## Testing Architecture

Backend tests live in `backend/tests`.

Key test structure:

```text
backend/tests/conftest.py              shared fixtures
backend/tests/api/routes/              route tests
backend/tests/crud/                    CRUD tests
backend/tests/scripts/                 startup script tests
backend/tests/utils/                   test data and auth helpers
```

`conftest.py` provides:

- a session-scoped database fixture that initializes first-superuser data,
- a FastAPI `TestClient`,
- superuser auth headers,
- normal-user auth headers.

Route tests call the API through `TestClient`, not directly through route functions. That means they exercise routing, dependency injection, authentication, serialization, and database behavior together.

The main backend validation commands are:

```bash
cd backend
bash scripts/test.sh
bash scripts/lint.sh
```

`scripts/test.sh` runs pytest through coverage and writes HTML coverage output. `scripts/lint.sh` runs mypy, ty, Ruff linting, and Ruff format checks.

## Error Handling Conventions

The backend mostly uses FastAPI's standard `HTTPException`.

Common status codes:

- `400`: invalid login, inactive user, incorrect password, invalid reset token, duplicate user creation in some endpoints.
- `403`: invalid credentials or insufficient privileges.
- `404`: missing user or item.
- `409`: email conflict during update.

Validation errors for request bodies, query parameters, and path parameters are handled automatically by FastAPI and Pydantic.

## Security Conventions

Important security decisions in this backend:

- Passwords are never returned through public schemas.
- New passwords are hashed before being stored.
- Password verification supports hash upgrades.
- Missing-user authentication runs dummy password verification to reduce timing differences.
- JWTs are signed with `SECRET_KEY`.
- Placeholder secrets are rejected outside local development.
- Password recovery does not reveal whether an email exists.
- Superuser checks are implemented as reusable dependencies.
- Local-only private routes are gated by `ENVIRONMENT == "local"`.

When changing authentication, authorization, password handling, email reset logic, or environment configuration, add focused backend tests and review deployment impact.

## Adding a New Backend Feature

For a new database-backed resource, follow this path:

1. Add table and schema classes in `backend/app/models.py`.
2. Create an Alembic migration under `backend/app/alembic/versions`.
3. Add reusable data operations in `backend/app/crud.py` if needed.
4. Add a route module under `backend/app/api/routes`.
5. Include the router in `backend/app/api/main.py`.
6. Use `SessionDep`, `CurrentUser`, or `get_current_active_superuser` for database and auth dependencies.
7. Return explicit response models so the OpenAPI contract stays clear.
8. Add tests in `backend/tests/api/routes` or `backend/tests/crud`.
9. Regenerate the frontend client with `bash scripts/generate-client.sh` if the API contract changed.
10. Run backend tests and lint checks.

## Where to Put Logic

Use these guidelines to keep the codebase consistent:

- Put environment and settings validation in `core/config.py`.
- Put database engine/session setup in `core/db.py` and `api/deps.py`.
- Put password and token primitives in `core/security.py`.
- Put table definitions and API schemas in `models.py`.
- Put shared database operations in `crud.py`.
- Put endpoint orchestration and permission checks in route modules.
- Put email rendering, email sending, and reset-token helpers in `utils.py`.
- Put migrations in `app/alembic/versions`.
- Put test-only object creation helpers in `backend/tests/utils`.

If logic is used by exactly one endpoint and is mostly about request handling, keeping it in the route module is acceptable. If logic is reused, security-sensitive, or needs isolated tests, move it into a helper such as `crud.py`, `security.py`, or `utils.py`.

## Mental Model

The backend can be understood as three concentric layers:

```text
HTTP layer
  FastAPI app, routers, dependencies, response models

Application/data layer
  route orchestration, CRUD helpers, authorization decisions

Infrastructure layer
  settings, database engine, migrations, email delivery, Sentry, Docker startup
```

Most feature work touches the first two layers: models, migrations, routes, CRUD helpers, and tests. Infrastructure files should change less often and deserve extra care because they affect startup, deployments, security, and generated frontend contracts.
