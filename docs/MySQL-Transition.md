# PostgreSQL to MySQL Transition

This document records the process used to move this stack from PostgreSQL to MySQL and the follow-up debugging work needed to make the backend, frontend, Docker stack, and local Traefik setup behave correctly.

## Scope

The transition touched:

- Docker database service and local port mapping.
- Backend database driver and settings.
- Alembic migrations that previously assumed PostgreSQL.
- SQLModel UUID handling in authentication and tests.
- MySQL transaction visibility in tests.
- Frontend stale-token handling after database resets.
- Local Traefik labels inherited from the production compose file.

## Stack Changes

### Docker Compose

The base database service was changed from PostgreSQL to MySQL:

```yaml
db:
  image: mysql:8.4
  healthcheck:
    test: ["CMD-SHELL", "mysqladmin ping -h 127.0.0.1 -u$${MYSQL_USER} -p$${MYSQL_PASSWORD} --silent"]
  volumes:
    - app-mysql-data:/var/lib/mysql
  environment:
    - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD?Variable not set}
    - MYSQL_DATABASE=${MYSQL_DB?Variable not set}
    - MYSQL_USER=${MYSQL_USER?Variable not set}
    - MYSQL_PASSWORD=${MYSQL_PASSWORD?Variable not set}
```

Backend and prestart services were changed to pass `MYSQL_*` variables and point `MYSQL_SERVER` at the Compose service name `db`.

The local override exposes MySQL on host port `3307` by default:

```yaml
db:
  ports:
    - "${MYSQL_HOST_PORT:-3307}:3306"
```

Use `MYSQL_PORT=3307` when running backend tests from the host against the running Compose database.

### Backend Dependency

The backend driver dependency changed from PostgreSQL to MySQL:

```toml
pymysql[rsa]<2.0.0,>=1.1.0
```

The settings layer should build a MySQL SQLAlchemy URI:

```text
mysql+pymysql://app:<password>@<host>:<port>/<db>
```

In containers, the host is `db` and port is `3306`. From the host test environment, the port is normally `3307`.

### Engine Isolation

MySQL's default `REPEATABLE READ` isolation made long-lived test sessions miss writes committed by request-scoped sessions. The engine was changed to use `READ COMMITTED`:

```python
engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    isolation_level="READ COMMITTED",
)
```

This made tests that create or modify data through API requests observe the committed data from the fixture session.

## Alembic Migration Updates

The UUID migration originally assumed PostgreSQL behavior:

- `uuid_generate_v4()`
- `postgresql.UUID(as_uuid=True)`
- PostgreSQL quoted `"user"` table names
- PostgreSQL primary key constraint names
- PostgreSQL sequences during downgrade

The migration was made dialect-aware:

- Use `postgresql.UUID(as_uuid=True)` on PostgreSQL.
- Use `sa.Uuid()` on MySQL/MariaDB.
- Use `uuid_generate_v4()` on PostgreSQL.
- Use `REPLACE(UUID(), '-', '')` on MySQL/MariaDB.
- Quote the reserved `user` table as `` `user` `` on MySQL.
- Drop MySQL primary keys with the constraint name `PRIMARY`.
- Remove integer `AUTO_INCREMENT` before replacing integer IDs with UUIDs.
- Use MySQL session variables to synthesize integer IDs during downgrade.

The critical lesson is that migrations which manipulate primary keys and foreign keys cannot assume PostgreSQL naming, quoting, UUID functions, or sequence behavior.

## UUID Binding Error

### Symptom

The backend raised:

```text
sqlalchemy.exc.StatementError: (builtins.AttributeError) 'str' object has no attribute 'hex'

[SQL: SELECT user.email AS user_email, ...
FROM user
WHERE user.id = %(pk_1)s]
[parameters: [{'pk_1': 'c29070e9-8e8c-42dc-8183-58f6cc6952db'}]]
```

### Cause

`User.id` is a `uuid.UUID` SQLModel field. With MySQL's SQLAlchemy UUID processor, passing a plain string to a UUID bind parameter fails because SQLAlchemy expects an object with `.hex`.

The failure happened in the authentication dependency:

```python
user = session.get(User, token_data.sub)
```

JWT `sub` values are serialized strings, so `token_data.sub` was a string unless explicitly validated or converted.

### Fix

`TokenPayload.sub` was changed to `uuid.UUID`, and `get_current_user()` explicitly converts the token subject before `session.get()`:

```python
token_data = TokenPayload(**payload)
user_id = uuid.UUID(str(token_data.sub))
user = session.get(User, user_id)
```

Invalid UUID subjects now raise the same credential validation error as invalid tokens.

### Regression Test

A login route test was added with a non-UUID token subject. It verifies that invalid token subjects return `403` instead of reaching SQLAlchemy.

## Test Query UUID Error

### Symptom

The full backend suite found the same UUID bind error in a test:

```python
select(User).where(User.id == data["id"])
```

`data["id"]` came from JSON, so it was a string.

### Fix

Convert response IDs back to UUID objects before comparing against UUID columns:

```python
select(User).where(User.id == uuid.UUID(data["id"]))
```

## Password Update Cleanup

While validating the login suite, password-related tests exposed stale reads and a small update-shape issue.

The stale reads were addressed by `READ COMMITTED`.

The update payload was also cleaned up so the raw `password` field is not passed into `sqlmodel_update()`:

```python
if "password" in user_data:
    password = user_data.pop("password")
    extra_data["hashed_password"] = get_password_hash(password)
```

## Frontend Items Page 404

### Symptom

After the MySQL/UUID backend error was fixed, the Items page still failed in the browser console:

```text
ApiError: Not Found
readItems
```

Backend logs showed:

```text
GET /api/v1/users/me -> 404
GET /api/v1/items/?skip=0&limit=100 -> 404
```

### Cause

The browser had a stale `access_token` for a user ID that no longer existed in MySQL. This often happens after test cleanup, database resets, migration experiments, or manual row deletion.

The backend behavior was correct: the token decoded, but `session.get(User, user_id)` found no user and returned `404 {"detail":"User not found"}`.

The frontend only treated `401` and `403` as invalid sessions, so `404 User not found` stayed as an unhandled query error on the Items page.

### Fix

The global React Query error handler now treats `404` with `detail === "User not found"` as an invalid session:

```ts
const errorDetail = (error.body as { detail?: unknown } | undefined)?.detail
const isInvalidSession =
  [401, 403].includes(error.status) ||
  (error.status === 404 && errorDetail === "User not found")

if (isInvalidSession) {
  localStorage.removeItem("access_token")
  window.location.href = "/login"
}
```

This preserves normal 404 behavior for other resources while recovering from stale auth tokens.

## Traefik Local Errors

### Symptom

Local Traefik logged:

```text
Router uses a nonexistent certificate resolver certificateResolver=le
```

It also warned:

```text
Could not find network named "traefik-public"
```

### Cause

The production labels in `compose.yml` include HTTPS routers with:

```text
tls.certresolver=le
```

The local Traefik service in `compose.override.yml` did not define a resolver named `le`. Defining a local ACME resolver is not the right fix because Traefik then tries to obtain public certificates for `*.localhost`.

The network warning happened because production labels referenced `traefik-public`, while the local Compose network was created with the project prefix.

### Fix

For local development, override the inherited certresolver labels to empty:

```yaml
adminer:
  labels:
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-https.tls.certresolver=

backend:
  labels:
    - traefik.http.routers.${STACK_NAME?Variable not set}-backend-https.tls.certresolver=

frontend:
  labels:
    - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-https.tls.certresolver=
```

Give the local network the same name the labels expect:

```yaml
networks:
  traefik-public:
    name: traefik-public
    external: false
```

After recreating the routed services, the nonexistent resolver and missing network errors disappeared. The remaining Traefik warnings are local development noise from the dummy `https-redirect` content-type middleware.

## Rebuild Notes

The local `docker compose up -d --build backend` path failed because the available Docker CLI did not load BuildKit/buildx plugins, while the backend Dockerfile uses BuildKit mounts.

The working rebuild path was:

```bash
/mnt/wsl/docker-desktop/cli-tools/usr/local/lib/docker/cli-plugins/docker-buildx build \
  -f backend/Dockerfile \
  -t backend:latest \
  --load \
  .
```

For frontend:

```bash
/mnt/wsl/docker-desktop/cli-tools/usr/local/lib/docker/cli-plugins/docker-buildx build \
  -f frontend/Dockerfile \
  -t frontend:latest \
  --build-arg VITE_API_URL=http://localhost:8000 \
  --build-arg NODE_ENV=development \
  --load \
  .
```

Then recreate services without rebuilding:

```bash
/mnt/wsl/docker-desktop/cli-tools/usr/local/lib/docker/cli-plugins/docker-compose up -d --no-build backend frontend
```

## Validation Checklist

### Compose State

```bash
/mnt/wsl/docker-desktop/cli-tools/usr/local/lib/docker/cli-plugins/docker-compose ps
```

Expected:

- `db` is healthy.
- `backend` is healthy.
- `frontend` is running.
- `proxy` is running if local Traefik is enabled.

### Backend Tests

Run from `backend/`:

```bash
MYSQL_PORT=3307 ../.venv/bin/pytest -q
```

Expected result:

```text
61 passed
```

### Backend Lint and Type Checks

Run from `backend/`:

```bash
PATH=../.venv/bin:$PATH bash scripts/lint.sh
```

Expected:

- mypy passes.
- ty passes.
- ruff check passes.
- ruff format check passes.

### API Health

```bash
python3 - <<'PY'
from urllib.request import urlopen
with urlopen("http://localhost:8000/api/v1/utils/health-check/", timeout=10) as response:
    print(response.status)
    print(response.read().decode())
PY
```

Expected:

```text
200
true
```

### Items API Flow

1. Ensure the first superuser exists:

```bash
/mnt/wsl/docker-desktop/cli-tools/usr/local/lib/docker/cli-plugins/docker-compose exec -T backend python - <<'PY'
from sqlmodel import Session
from app.core.config import settings
from app.core.db import engine, init_db
from app.crud import get_user_by_email

with Session(engine) as session:
    init_db(session)
    user = get_user_by_email(session=session, email=str(settings.FIRST_SUPERUSER))
    print("superuser_seeded", bool(user))
PY
```

2. Login and call `/users/me` plus `/items/`:

```bash
python3 - <<'PY'
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

base = "http://localhost:8000/api/v1"
email = "admin@example.com"
password = "changethis"

def request(path, *, method="GET", token=None, data=None, content_type="application/json"):
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        if content_type == "application/json":
            body = json.dumps(data).encode()
            headers["Content-Type"] = content_type
        else:
            body = urlencode(data).encode()
            headers["Content-Type"] = content_type
    req = Request(f"{base}{path}", data=body, headers=headers, method=method)
    with urlopen(req, timeout=10) as response:
        raw = response.read().decode()
        return response.status, json.loads(raw) if raw else None

login_status, login_body = request(
    "/login/access-token",
    method="POST",
    data={"username": email, "password": password},
    content_type="application/x-www-form-urlencoded",
)
token = login_body["access_token"]
print("login_status", login_status)
print("me_status", request("/users/me", token=token)[0])
print("items_status", request("/items/?skip=0&limit=100", token=token)[0])
PY
```

Expected:

```text
login_status 200
me_status 200
items_status 200
```

### Direct SQLModel Query Validation

Use real UUID objects when querying UUID columns:

```python
import uuid
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User

with Session(engine) as session:
    user = session.get(User, uuid.UUID("<user-id>"))
```

Do not pass JSON response ID strings directly into `session.get()` or `User.id == ...`.

## Common Failure Patterns

### `str object has no attribute hex`

Cause: string passed to a UUID bind parameter.

Fix: validate or convert to `uuid.UUID` before querying UUID columns.

### Items Page `ApiError: Not Found`

Cause: stale browser token references a user that no longer exists.

Fix: clear `localStorage.access_token`, log in again, or rely on the frontend invalid-session handler.

### Host Tests Cannot Connect to MySQL

Cause: host tests use default MySQL port `3306`, but Compose publishes MySQL on `3307`.

Fix:

```bash
MYSQL_PORT=3307 ../.venv/bin/pytest -q
```

### Traefik Nonexistent Resolver

Cause: production HTTPS labels reference `le`, but local Traefik does not define it.

Fix: override local HTTPS certresolver labels to empty in `compose.override.yml`.

### Traefik Missing Network

Cause: labels reference `traefik-public`, but local Compose created a prefixed network name.

Fix:

```yaml
networks:
  traefik-public:
    name: traefik-public
    external: false
```

## Operational Notes

- Tests may delete users during cleanup. After running the full backend suite against the shared local MySQL database, reseed the first superuser with `init_db()`.
- Browser tokens can outlive database rows. If pages fail immediately after database resets, stale auth state is the first thing to check.
- Generated frontend client files should not be edited manually. If backend API contracts change, regenerate the client with `bash scripts/generate-client.sh`.
- Prefer `docker-buildx build --load` in this environment when Dockerfiles use BuildKit mounts and the normal Compose build path cannot load BuildKit.
