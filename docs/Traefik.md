# Traefik and Request Routing

This project uses Traefik as the Docker-aware reverse proxy for subdomain-based routing. The base stack describes how each service should be routed with Traefik labels, the local override adds a development proxy, and `compose.traefik.yml` defines the standalone public Traefik used for deployments.

The important distinction:

- In local development, the frontend usually calls the backend directly at `http://localhost:8000`.
- In production, browser traffic enters through Traefik and is routed by hostname, for example `api.${DOMAIN}` and `dashboard.${DOMAIN}`.

## `compose.yml`

`compose.yml` is the base application stack. It does not define the Traefik container itself, but it defines the Traefik labels that tell Traefik how to route to `adminer`, `backend`, and `frontend`.

### `adminer`

```yaml
adminer:
  image: adminer
  restart: always
  networks:
    - traefik-public
    - default
  depends_on:
    - db
  environment:
    - ADMINER_DESIGN=pepa-linha-dark
  labels:
    - traefik.enable=true
    - traefik.docker.network=traefik-public
    - traefik.constraint-label=traefik-public
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-http.rule=Host(`adminer.${DOMAIN?Variable not set}`)
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-http.entrypoints=http
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-http.middlewares=https-redirect
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-https.rule=Host(`adminer.${DOMAIN?Variable not set}`)
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-https.entrypoints=https
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-https.tls=true
    - traefik.http.routers.${STACK_NAME?Variable not set}-adminer-https.tls.certresolver=le
    - traefik.http.services.${STACK_NAME?Variable not set}-adminer.loadbalancer.server.port=8080
```

What this does:

- `traefik.enable=true` opts the Adminer container into Traefik routing.
- `traefik.docker.network=traefik-public` tells Traefik to reach this container through the `traefik-public` Docker network.
- `traefik.constraint-label=traefik-public` lets the local development proxy filter for services that belong to this stack.
- `Host(\`adminer.${DOMAIN}\`)` matches requests to the Adminer subdomain.
- `loadbalancer.server.port=8080` tells Traefik to forward matching requests to port `8080` inside the Adminer container.
- The HTTP router uses the `https-redirect` middleware. In production, that middleware redirects to HTTPS. In local development, the override file replaces it with a harmless dummy middleware.

### `backend`

```yaml
backend:
  image: '${DOCKER_IMAGE_BACKEND?Variable not set}:${TAG-latest}'
  restart: always
  networks:
    - traefik-public
    - default
  depends_on:
    db:
      condition: service_healthy
      restart: true
    prestart:
      condition: service_completed_successfully
  env_file:
    - .env
  environment:
    - DOMAIN=${DOMAIN}
    - FRONTEND_HOST=${FRONTEND_HOST?Variable not set}
    - ENVIRONMENT=${ENVIRONMENT}
    - BACKEND_CORS_ORIGINS=${BACKEND_CORS_ORIGINS}
```

The backend receives routing and CORS-related environment variables from `.env`.

The backend Traefik labels are:

```yaml
labels:
  - traefik.enable=true
  - traefik.docker.network=traefik-public
  - traefik.constraint-label=traefik-public

  - traefik.http.services.${STACK_NAME?Variable not set}-backend.loadbalancer.server.port=8000

  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-http.rule=Host(`api.${DOMAIN?Variable not set}`)
  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-http.entrypoints=http

  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-https.rule=Host(`api.${DOMAIN?Variable not set}`)
  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-https.entrypoints=https
  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-https.tls=true
  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-https.tls.certresolver=le

  # Enable redirection for HTTP and HTTPS
  - traefik.http.routers.${STACK_NAME?Variable not set}-backend-http.middlewares=https-redirect
```

What this does:

- Requests with host `api.${DOMAIN}` match the backend router.
- On the HTTP entrypoint, Traefik applies `https-redirect`.
- On the HTTPS entrypoint, Traefik enables TLS and uses the `le` certificate resolver.
- Matching requests are forwarded to backend container port `8000`.

For example, if `DOMAIN=fastapi-project.example.com`, the backend route is:

```text
https://api.fastapi-project.example.com -> backend:8000
```

### `frontend`

```yaml
frontend:
  image: '${DOCKER_IMAGE_FRONTEND?Variable not set}:${TAG-latest}'
  restart: always
  networks:
    - traefik-public
    - default
  build:
    context: .
    dockerfile: frontend/Dockerfile
    args:
      - VITE_API_URL=https://api.${DOMAIN?Variable not set}
      - NODE_ENV=production
```

The production-like frontend build bakes this API URL into the generated JavaScript bundle:

```text
VITE_API_URL=https://api.${DOMAIN}
```

The frontend Traefik labels are:

```yaml
labels:
  - traefik.enable=true
  - traefik.docker.network=traefik-public
  - traefik.constraint-label=traefik-public

  - traefik.http.services.${STACK_NAME?Variable not set}-frontend.loadbalancer.server.port=80

  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-http.rule=Host(`dashboard.${DOMAIN?Variable not set}`)
  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-http.entrypoints=http

  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-https.rule=Host(`dashboard.${DOMAIN?Variable not set}`)
  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-https.entrypoints=https
  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-https.tls=true
  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-https.tls.certresolver=le

  # Enable redirection for HTTP and HTTPS
  - traefik.http.routers.${STACK_NAME?Variable not set}-frontend-http.middlewares=https-redirect
```

What this does:

- Requests with host `dashboard.${DOMAIN}` match the frontend router.
- Matching requests are forwarded to frontend container port `80`.
- HTTP requests are redirected to HTTPS in production.
- HTTPS uses the same `le` Let's Encrypt certificate resolver.

For example:

```text
https://dashboard.fastapi-project.example.com -> frontend:80
```

### Network

```yaml
networks:
  traefik-public:
    # Allow setting it to false for testing
    external: true
```

In the base stack, `traefik-public` is external. Docker Compose expects this network to already exist. The public Traefik container and the app containers share this network so Traefik can reach the app services.

## `compose.override.yml`

`compose.override.yml` is automatically applied by Docker Compose for local development. It adds a local Traefik proxy named `proxy`, exposes app ports directly on localhost, and changes frontend API configuration for local use.

### Local `proxy`

```yaml
# Local services are available on their ports, but also available on:
# http://api.localhost.tiangolo.com: backend
# http://dashboard.localhost.tiangolo.com: frontend
# etc. To enable it, update .env, set:
# DOMAIN=localhost.tiangolo.com
proxy:
  image: traefik:3.6
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
  ports:
    - "80:80"
    - "8090:8080"
```

What this does:

- Starts a local Traefik container named `proxy`.
- Publishes local host port `80` to Traefik's HTTP entrypoint.
- Publishes local host port `8090` to Traefik's dashboard/API port `8080`.
- Mounts the Docker socket so Traefik can read labels from the other Compose services.

The local Traefik command is:

```yaml
command:
  # Enable Docker in Traefik, so that it reads labels from Docker services
  - --providers.docker
  # Add a constraint to only use services with the label for this stack
  - --providers.docker.constraints=Label(`traefik.constraint-label`, `traefik-public`)
  # Do not expose all Docker services, only the ones explicitly exposed
  - --providers.docker.exposedbydefault=false
  # Create an entrypoint "http" listening on port 80
  - --entrypoints.http.address=:80
  # Create an entrypoint "https" listening on port 443
  - --entrypoints.https.address=:443
  # Enable the access log, with HTTP requests
  - --accesslog
  # Enable the Traefik log, for configurations and errors
  - --log
  # Enable debug logging for local development
  - --log.level=DEBUG
  # Enable the Dashboard and API
  - --api
  # Enable the Dashboard and API in insecure mode for local development
  - --api.insecure=true
```

What this does:

- `--providers.docker` enables Docker label discovery.
- `--providers.docker.constraints=Label(\`traefik.constraint-label\`, \`traefik-public\`)` tells local Traefik to only route services with that label.
- `--providers.docker.exposedbydefault=false` prevents accidental exposure of unlabeled containers.
- `--entrypoints.http.address=:80` creates the local HTTP entrypoint.
- `--api.insecure=true` exposes the local dashboard without auth at `http://localhost:8090`.

The local proxy labels are:

```yaml
labels:
  # Enable Traefik for this service, to make it available in the public network
  - traefik.enable=true
  - traefik.constraint-label=traefik-public
  # Dummy https-redirect middleware that doesn't really redirect, only to
  # allow running it locally
  - traefik.http.middlewares.https-redirect.contenttype.autodetect=false
```

The important line is the dummy `https-redirect` middleware. The base file's routers refer to a middleware named `https-redirect`. In production, that middleware redirects HTTP to HTTPS. Locally, this dummy middleware exists only so those router references are valid without forcing HTTPS.

### Direct Local Ports

The local override exposes services directly:

```yaml
backend:
  restart: "no"
  ports:
    - "8000:8000"
```

This lets the browser call the backend directly at:

```text
http://localhost:8000
```

The local frontend override is:

```yaml
frontend:
  restart: "no"
  ports:
    - "5173:80"
  build:
    context: .
    dockerfile: frontend/Dockerfile
    args:
      - VITE_API_URL=http://localhost:8000
      - NODE_ENV=development
```

This serves the built frontend at:

```text
http://localhost:5173
```

and bakes this backend URL into the frontend bundle:

```text
http://localhost:8000
```

So in normal local Docker development, API calls bypass Traefik.

### Playwright API URL

```yaml
playwright:
  build:
    context: .
    dockerfile: frontend/Dockerfile.playwright
    args:
      - VITE_API_URL=http://backend:8000
      - NODE_ENV=production
  environment:
    - VITE_API_URL=http://backend:8000
```

The Playwright container runs inside Docker, so it reaches the backend by Docker service name:

```text
http://backend:8000
```

### Local Network

```yaml
networks:
  traefik-public:
    # For local dev, don't expect an external Traefik network
    external: false
```

The override changes `traefik-public` from an external network to a Compose-managed local network. This is why local development does not require running `docker network create traefik-public`.

## `compose.traefik.yml`

`compose.traefik.yml` defines the public Traefik service used in deployments. It is intentionally separate from the app stack so one Traefik instance can route traffic for one or more deployed stacks.

### Public Ports

```yaml
services:
  traefik:
    image: traefik:3.6
    ports:
      # Listen on port 80, default for HTTP, necessary to redirect to HTTPS
      - 80:80
      # Listen on port 443, default for HTTPS
      - 443:443
    restart: always
```

This makes Traefik the public entrypoint for HTTP and HTTPS traffic on the server.

### Dashboard Route

```yaml
labels:
  # Enable Traefik for this service, to make it available in the public network
  - traefik.enable=true
  # Use the traefik-public network (declared below)
  - traefik.docker.network=traefik-public
  # Define the port inside of the Docker service to use
  - traefik.http.services.traefik-dashboard.loadbalancer.server.port=8080
  # Make Traefik use this domain (from an environment variable) in HTTP
  - traefik.http.routers.traefik-dashboard-http.entrypoints=http
  - traefik.http.routers.traefik-dashboard-http.rule=Host(`traefik.${DOMAIN?Variable not set}`)
  # traefik-https the actual router using HTTPS
  - traefik.http.routers.traefik-dashboard-https.entrypoints=https
  - traefik.http.routers.traefik-dashboard-https.rule=Host(`traefik.${DOMAIN?Variable not set}`)
  - traefik.http.routers.traefik-dashboard-https.tls=true
  # Use the "le" (Let's Encrypt) resolver created below
  - traefik.http.routers.traefik-dashboard-https.tls.certresolver=le
  # Use the special Traefik service api@internal with the web UI/Dashboard
  - traefik.http.routers.traefik-dashboard-https.service=api@internal
```

This exposes the Traefik dashboard at:

```text
https://traefik.${DOMAIN}
```

The dashboard is routed to Traefik's internal service:

```text
api@internal
```

### HTTPS Redirect and Dashboard Auth

```yaml
labels:
  # https-redirect middleware to redirect HTTP to HTTPS
  - traefik.http.middlewares.https-redirect.redirectscheme.scheme=https
  - traefik.http.middlewares.https-redirect.redirectscheme.permanent=true
  # traefik-http set up only to use the middleware to redirect to https
  - traefik.http.routers.traefik-dashboard-http.middlewares=https-redirect
  # admin-auth middleware with HTTP Basic auth
  # Using the environment variables USERNAME and HASHED_PASSWORD
  - traefik.http.middlewares.admin-auth.basicauth.users=${USERNAME?Variable not set}:${HASHED_PASSWORD?Variable not set}
  # Enable HTTP Basic auth, using the middleware created above
  - traefik.http.routers.traefik-dashboard-https.middlewares=admin-auth
```

This creates:

- a real production `https-redirect` middleware,
- HTTP Basic Auth for the Traefik dashboard.

The app stack's HTTP routers also reference the middleware named `https-redirect`, so this production Traefik definition supplies that middleware.

### Docker Provider and Let's Encrypt

```yaml
volumes:
  # Add Docker as a mounted volume, so that Traefik can read the labels of other services
  - /var/run/docker.sock:/var/run/docker.sock:ro
  # Mount the volume to store the certificates
  - traefik-public-certificates:/certificates
command:
  # Enable Docker in Traefik, so that it reads labels from Docker services
  - --providers.docker
  # Do not expose all Docker services, only the ones explicitly exposed
  - --providers.docker.exposedbydefault=false
  # Create an entrypoint "http" listening on port 80
  - --entrypoints.http.address=:80
  # Create an entrypoint "https" listening on port 443
  - --entrypoints.https.address=:443
  # Create the certificate resolver "le" for Let's Encrypt, uses the environment variable EMAIL
  - --certificatesresolvers.le.acme.email=${EMAIL?Variable not set}
  # Store the Let's Encrypt certificates in the mounted volume
  - --certificatesresolvers.le.acme.storage=/certificates/acme.json
  # Use the TLS Challenge for Let's Encrypt
  - --certificatesresolvers.le.acme.tlschallenge=true
  # Enable the access log, with HTTP requests
  - --accesslog
  # Enable the Traefik log, for configurations and errors
  - --log
  # Enable the Dashboard and API
  - --api
```

What this does:

- Reads Docker service labels from the Docker socket.
- Exposes only services with `traefik.enable=true`.
- Listens on entrypoints named `http` and `https`.
- Creates a certificate resolver named `le`.
- Uses the TLS challenge to obtain Let's Encrypt certificates.
- Stores certificates in the `traefik-public-certificates` volume.

### Public Network

```yaml
volumes:
  # Create a volume to store the certificates, even if the container is recreated
  traefik-public-certificates:

networks:
  # Use the previously created public network "traefik-public", shared with other
  # services that need to be publicly available via this Traefik
  traefik-public:
    external: true
```

The deployment docs instruct creating this network before starting the stacks:

```bash
docker network create traefik-public
```

## `.env`

The root `.env` defines the variables used by Compose and by the backend.

Relevant local values:

```dotenv
# Domain
# This would be set to the production domain with an env var on deployment
# used by Traefik to transmit traffic and aqcuire TLS certificates
DOMAIN=localhost
# To test the local Traefik config
# DOMAIN=localhost.tiangolo.com

# Used by the backend to generate links in emails to the frontend
FRONTEND_HOST=http://localhost:5173
# In staging and production, set this env var to the frontend host, e.g.
# FRONTEND_HOST=https://dashboard.example.com

# Environment: local, staging, production
ENVIRONMENT=local

PROJECT_NAME="Full Stack FastAPI Project"
STACK_NAME=full-stack-fastapi-project

# Backend
BACKEND_CORS_ORIGINS="http://localhost,http://localhost:5173,https://localhost,https://localhost:5173,http://localhost.tiangolo.com"
```

What these do:

- `DOMAIN` is interpolated into Traefik host rules such as `api.${DOMAIN}` and `dashboard.${DOMAIN}`.
- `FRONTEND_HOST` is used by the backend for frontend links and CORS.
- `STACK_NAME` is interpolated into Traefik router and service names.
- `BACKEND_CORS_ORIGINS` controls which browser origins can call the backend.

With the default local value:

```text
DOMAIN=localhost
```

the Traefik host rules become:

```text
api.localhost
dashboard.localhost
adminer.localhost
```

To test local subdomain routing, the comment tells you to use:

```dotenv
DOMAIN=localhost.tiangolo.com
```

Then the routes become:

```text
api.localhost.tiangolo.com
dashboard.localhost.tiangolo.com
adminer.localhost.tiangolo.com
```

`localhost.tiangolo.com` and its subdomains resolve to `127.0.0.1`, so those hostnames reach the local machine.

## `frontend/.env`

```dotenv
VITE_API_URL=http://localhost:8000
MAILCATCHER_HOST=http://localhost:1080
```

When running the frontend with Vite locally, this makes the browser call the backend directly:

```text
http://localhost:8000
```

This bypasses Traefik for API requests.

## `frontend/src/main.tsx`

```ts
OpenAPI.BASE = import.meta.env.VITE_API_URL
OpenAPI.TOKEN = async () => {
  return localStorage.getItem("access_token") || ""
}
```

This is where the generated OpenAPI client receives its base URL.

Examples:

```text
Local Vite:       OpenAPI.BASE = http://localhost:8000
Local Docker:     OpenAPI.BASE = http://localhost:8000
Production build: OpenAPI.BASE = https://api.${DOMAIN}
Playwright:       OpenAPI.BASE = http://backend:8000
```

## `frontend/Dockerfile`

```dockerfile
COPY ./frontend /app/frontend
ARG VITE_API_URL

RUN bun run build
```

`VITE_API_URL` is a build argument. Vite reads it during `bun run build`, and the resulting static JavaScript bundle contains that value.

The final image serves static files with Nginx:

```dockerfile
FROM nginx:1

COPY --from=build-stage /app/frontend/dist/ /usr/share/nginx/html

COPY ./frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY ./frontend/nginx-backend-not-found.conf /etc/nginx/extra-conf.d/backend-not-found.conf
```

This Nginx container serves the frontend. It is not the API reverse proxy.

## `frontend/nginx.conf`

```nginx
server {
  listen 80;

  location / {
    root /usr/share/nginx/html;
    index index.html index.htm;
    try_files $uri /index.html =404;
  }

  include /etc/nginx/extra-conf.d/*.conf;
}
```

This serves the single-page app from `/usr/share/nginx/html`. Unknown frontend routes fall back to `index.html`.

## `frontend/nginx-backend-not-found.conf`

```nginx
location /api {
    return 404;
}
location /docs {
    return 404;
}
location /redoc {
    return 404;
}
```

This explicitly prevents the frontend Nginx container from acting as a backend proxy.

These URLs will return `404` from the frontend container:

```text
https://dashboard.${DOMAIN}/api
https://dashboard.${DOMAIN}/docs
https://dashboard.${DOMAIN}/redoc
```

The frontend must call the backend host instead:

```text
https://api.${DOMAIN}
```

## `backend/app/core/config.py`

```py
model_config = SettingsConfigDict(
    # Use top level .env file (one level above ./backend/)
    env_file="../.env",
    env_ignore_empty=True,
    extra="ignore",
)
```

The backend reads the root `.env`.

CORS-related settings:

```py
FRONTEND_HOST: str = "http://localhost:5173"
ENVIRONMENT: Literal["local", "staging", "production"] = "local"

BACKEND_CORS_ORIGINS: Annotated[
    list[AnyUrl] | str, BeforeValidator(parse_cors)
] = []

@computed_field  # type: ignore[prop-decorator]
@property
def all_cors_origins(self) -> list[str]:
    return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
        self.FRONTEND_HOST
    ]
```

This creates the final list of allowed browser origins by combining `BACKEND_CORS_ORIGINS` with `FRONTEND_HOST`.

## `backend/app/main.py`

```py
# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

The backend applies CORS using the values from `.env`.

This matters because production frontend and backend are on different origins:

```text
https://dashboard.${DOMAIN}
https://api.${DOMAIN}
```

The browser treats those as cross-origin requests, so the backend must allow the frontend origin.

## Development Request Flow

### Default Local Docker Flow

The default local Docker path exposes the frontend and backend directly with ports from `compose.override.yml`.

```text
Browser
  |
  | GET http://localhost:5173
  v
host port 5173
  |
  v
frontend container nginx:80
  |
  | frontend JS has VITE_API_URL=http://localhost:8000
  v
Browser
  |
  | API request http://localhost:8000/api/...
  v
host port 8000
  |
  v
backend container FastAPI:8000
```

Traefik is bypassed for the API call in this flow.

### Local Traefik Flow

If `.env` is changed to:

```dotenv
DOMAIN=localhost.tiangolo.com
```

then local Traefik can route subdomains through host port `80`.

Backend:

```text
Browser
  |
  | GET http://api.localhost.tiangolo.com
  v
DNS resolves to 127.0.0.1
  |
  v
host port 80
  |
  v
local Traefik service: proxy
  |
  | Host(`api.localhost.tiangolo.com`)
  v
backend container FastAPI:8000
```

Frontend:

```text
Browser
  |
  | GET http://dashboard.localhost.tiangolo.com
  v
DNS resolves to 127.0.0.1
  |
  v
host port 80
  |
  v
local Traefik service: proxy
  |
  | Host(`dashboard.localhost.tiangolo.com`)
  v
frontend container nginx:80
```

Important detail: even when the frontend page is loaded through local Traefik, the local Docker frontend build still uses:

```text
VITE_API_URL=http://localhost:8000
```

So frontend API calls still go directly to `localhost:8000` unless you change `VITE_API_URL`.

## Production Request Flow

Production uses the standalone Traefik from `compose.traefik.yml` plus the app stack from `compose.yml`.

### Frontend Page Request

```text
Browser
  |
  | GET https://dashboard.fastapi-project.example.com
  v
public DNS
  |
  v
server port 443
  |
  v
Traefik from compose.traefik.yml
  |
  | Host(`dashboard.${DOMAIN}`)
  v
frontend container nginx:80
```

### API Request

The production frontend build uses:

```text
VITE_API_URL=https://api.${DOMAIN}
```

So browser API calls flow like this:

```text
Browser running frontend JS
  |
  | API request https://api.fastapi-project.example.com/api/...
  v
public DNS
  |
  v
server port 443
  |
  v
Traefik from compose.traefik.yml
  |
  | Host(`api.${DOMAIN}`)
  v
backend container FastAPI:8000
```

### HTTP Redirect

For HTTP requests:

```text
Browser
  |
  | GET http://api.fastapi-project.example.com
  v
Traefik http entrypoint :80
  |
  | middleware: https-redirect
  v
301/308 redirect to https://api.fastapi-project.example.com
```

The redirect middleware is defined in `compose.traefik.yml`:

```yaml
- traefik.http.middlewares.https-redirect.redirectscheme.scheme=https
- traefik.http.middlewares.https-redirect.redirectscheme.permanent=true
```

## How `api.${DOMAIN}` Is Resolved

This repository does not perform DNS resolution. It only configures hostnames in Traefik labels.

In local development:

```dotenv
DOMAIN=localhost.tiangolo.com
```

produces:

```text
api.localhost.tiangolo.com
```

That domain resolves to `127.0.0.1`, so the request reaches the local Traefik proxy on host port `80`.

In production:

```bash
export DOMAIN=fastapi-project.example.com
```

produces:

```text
api.fastapi-project.example.com
```

The deployment docs expect DNS such as `*.fastapi-project.example.com` to point to the server running Traefik. Once the request reaches the server, Traefik uses the `Host` header to choose the backend router.

## How Traefik Chooses a Container

Traefik uses four pieces of information from this repo:

1. Docker provider:

```yaml
- --providers.docker
```

2. Docker socket:

```yaml
- /var/run/docker.sock:/var/run/docker.sock:ro
```

3. Opt-in service labels:

```yaml
- traefik.enable=true
```

4. Router, service, network, and port labels:

```yaml
- traefik.docker.network=traefik-public
- traefik.http.routers.${STACK_NAME?Variable not set}-backend-https.rule=Host(`api.${DOMAIN?Variable not set}`)
- traefik.http.services.${STACK_NAME?Variable not set}-backend.loadbalancer.server.port=8000
```

Together, these mean:

```text
When a request has Host: api.${DOMAIN},
route it through the traefik-public Docker network
to the backend container on port 8000.
```

## Development vs Production

| Concern | Development | Production |
| --- | --- | --- |
| Traefik container | `proxy` in `compose.override.yml` | `traefik` in `compose.traefik.yml` |
| Public ports | `80:80`, `8090:8080` | `80:80`, `443:443` |
| Dashboard | `http://localhost:8090`, insecure | `https://traefik.${DOMAIN}`, basic auth |
| Backend access | Usually `http://localhost:8000` directly | `https://api.${DOMAIN}` through Traefik |
| Frontend access | Usually `http://localhost:5173` directly | `https://dashboard.${DOMAIN}` through Traefik |
| Frontend API URL | `http://localhost:8000` | `https://api.${DOMAIN}` |
| HTTPS | Dummy redirect middleware | Real HTTPS redirect and Let's Encrypt |
| `traefik-public` network | Compose-managed, `external: false` | Pre-existing Docker network, `external: true` |
| DNS | Optional `localhost.tiangolo.com` test domain | Real DNS or wildcard DNS points to server |

## Summary

In this template, Traefik is not hardcoded into FastAPI or React. It is configured through Docker Compose labels.

The backend does not know that Traefik exists. It listens on port `8000`.

The frontend does not proxy API requests through its own Nginx container. It calls the API URL from `VITE_API_URL`.

Traefik's job is to:

- listen on public HTTP/HTTPS ports,
- inspect the request hostname,
- match that hostname against Docker labels,
- terminate HTTPS in production,
- redirect HTTP to HTTPS in production,
- forward the request to the matching container and port.

