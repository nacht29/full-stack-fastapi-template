# Docker Compose Files

This project uses `compose.yml` as the base stack and `compose.override.yml` as the local development overlay.

Docker Compose automatically reads both files for commands such as:

```bash
docker compose up
docker compose watch
```

Use only the base file when you want the production-like configuration without local overrides:

```bash
docker compose -f compose.yml up
```

## `compose.yml`

`compose.yml` defines the main application stack. It is production-like and assumes services are exposed through Traefik.

### `db`

The `db` service runs MySQL 8.4.

It configures:

- persistent storage through the `app-mysql-data` volume,
- a healthcheck using `mysqladmin ping`,
- database settings from `.env`,
- required `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, `MYSQL_USER`, and `MYSQL_DB` variables.

Other services depend on this healthcheck before starting database-backed work.

### `adminer`

The `adminer` service provides a database administration UI.

It depends on `db` and is attached to both the default network and `traefik-public`. In the base stack, it is exposed through Traefik at:

```text
adminer.${DOMAIN}
```

### `prestart`

The `prestart` service is a one-shot backend container.

It uses the backend image and runs:

```bash
bash scripts/prestart.sh
```

It waits for the database to become healthy, then performs startup preparation before the main backend service runs. This is commonly where migrations and first-user setup happen in this template.

### `backend`

The `backend` service runs the FastAPI application.

It configures:

- the backend image and `backend/Dockerfile` build,
- environment variables from `.env`,
- MySQL connection settings pointing at the `db` service,
- a healthcheck at `/api/v1/utils/health-check/`,
- dependency ordering on both `db` and `prestart`,
- Traefik routing for `api.${DOMAIN}`.

In the base stack, backend traffic is expected to flow through Traefik. The container listens internally on port `8000`, and Traefik forwards traffic to that port.

### `frontend`

The `frontend` service builds and serves the frontend application.

In the base stack, it builds with:

```text
VITE_API_URL=https://api.${DOMAIN}
NODE_ENV=production
```

It is exposed through Traefik at:

```text
dashboard.${DOMAIN}
```

The container serves the frontend internally on port `80`, and Traefik forwards traffic to that port.

### Networks and Volumes

The base file defines the `app-mysql-data` volume for MySQL data.

It also declares the `traefik-public` network as external:

```yaml
networks:
  traefik-public:
    external: true
```

That means the base stack expects this network to already exist, usually because Traefik is managed separately.

## `compose.override.yml`

`compose.override.yml` changes the base stack for local development. These overrides are applied automatically by Docker Compose unless you explicitly choose files with `-f`.

The main purpose of this file is to make services easy to access from localhost, enable backend reload behavior, add local email capture, and provide a Playwright test container.

### `proxy`

The override adds a local Traefik service named `proxy`.

It publishes:

```text
localhost:80    -> Traefik HTTP entrypoint
localhost:8090  -> Traefik dashboard/API
```

It mounts the Docker socket so Traefik can read service labels. It also enables local debug logging and the insecure Traefik dashboard API for development.

If `.env` sets:

```text
DOMAIN=localhost.tiangolo.com
```

the services are also available through hostnames such as:

```text
http://api.localhost.tiangolo.com
http://dashboard.localhost.tiangolo.com
```

### `db` Override

The local override changes `db` from a production-style service to a local one:

```yaml
restart: "no"
ports:
  - "${MYSQL_HOST_PORT:-3307}:3306"
```

This exposes MySQL directly on `localhost:3307` by default and prevents Docker from automatically restarting it after it exits. Set `MYSQL_HOST_PORT=3306` if you specifically want to expose it on the standard MySQL host port and nothing else is already using that port.

### `adminer` Override

The local override changes `adminer` to:

```yaml
restart: "no"
ports:
  - "8080:8080"
```

This makes Adminer directly available at:

```text
http://localhost:8080
```

It can still also be reached through local Traefik routing when the local domain setup is used.

### `backend` Override

The override changes the backend for development.

It publishes:

```text
localhost:8000 -> backend container port 8000
```

It changes the command to:

```bash
fastapi run --reload app/main.py
```

This enables reload behavior while developing the backend.

It also configures Docker Compose `develop.watch`:

- changes under `./backend` are synced into `/app/backend`,
- local virtual environments are ignored,
- changes to `./backend/pyproject.toml` trigger a rebuild.

The override mounts backend coverage output:

```text
./backend/htmlcov -> /app/backend/htmlcov
```

It also redirects email settings to Mailcatcher:

```text
SMTP_HOST=mailcatcher
SMTP_PORT=1025
SMTP_TLS=false
EMAILS_FROM_EMAIL=noreply@example.com
```

### `mailcatcher`

The override adds a `mailcatcher` service for local email testing.

It publishes:

```text
localhost:1080 -> Mailcatcher web UI
localhost:1025 -> Mailcatcher SMTP port
```

The backend sends email to this service in local Docker development, and captured messages can be viewed at:

```text
http://localhost:1080
```

### `frontend` Override

The local override changes the frontend restart policy, exposed port, and build arguments.

It publishes:

```text
localhost:5173 -> frontend container port 80
```

It builds with:

```text
VITE_API_URL=http://localhost:8000
NODE_ENV=development
```

This points the frontend directly at the locally exposed backend instead of the production-style `https://api.${DOMAIN}` URL.

### `playwright`

The override adds a `playwright` service for frontend end-to-end tests.

It builds from:

```text
frontend/Dockerfile.playwright
```

It depends on:

- `backend`,
- `mailcatcher`.

It sets:

```text
VITE_API_URL=http://backend:8000
MAILCATCHER_HOST=http://mailcatcher:1080
PLAYWRIGHT_HTML_HOST=0.0.0.0
```

It mounts local test artifacts:

```text
./frontend/blob-report  -> /app/frontend/blob-report
./frontend/test-results -> /app/frontend/test-results
```

It also publishes Playwright report access on:

```text
localhost:9323
```

### Network Override

The override changes `traefik-public` from an external network to a local Compose-managed network:

```yaml
networks:
  traefik-public:
    external: false
```

This lets the local `proxy` service and application services share the same network without requiring a pre-existing external Traefik network.

## Combined Local Result

When running the default local Compose setup, the effective stack includes:

- MySQL at `localhost:3307`,
- Adminer at `http://localhost:8080`,
- backend API at `http://localhost:8000`,
- frontend at `http://localhost:5173`,
- Mailcatcher at `http://localhost:1080`,
- Traefik dashboard at `http://localhost:8090`,
- Playwright report server at `http://localhost:9323` when the Playwright service is running.

The base file keeps the deployed service shape. The override file adapts that shape for day-to-day local development.
