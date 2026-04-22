#!/usr/bin/env bash

set -euo pipefail

docker_cli="${DOCKER_CLI:-/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker}"
profile="${PROFILE:-$HOME/.profile}"
marker="# Docker Desktop CLI for WSL"
docker_dir="$(dirname "$docker_cli")"

if [ ! -x "$docker_cli" ]; then
  echo "Docker CLI not found or not executable: $docker_cli" >&2
  exit 1
fi

touch "$profile"

if ! grep -qxF "$marker" "$profile"; then
  printf '\n%s\n' "$marker" >> "$profile"
  printf 'case ":$PATH:" in\n' >> "$profile"
  printf '  *:%s:*) ;;\n' "$docker_dir" >> "$profile"
  printf '  *) export PATH="%s:$PATH" ;;\n' "$docker_dir" >> "$profile"
  printf 'esac\n' >> "$profile"
  echo "Added Docker Desktop CLI PATH block to $profile"
else
  echo "Docker Desktop CLI PATH block already exists in $profile"
fi

# Some sandboxed shells use a generated first PATH directory and ignore the
# user's normal profile. If that directory is writable, add a temporary symlink.
path_head="${PATH%%:*}"
if [ -n "$path_head" ] && [ -d "$path_head" ] && [ -w "$path_head" ]; then
  ln -sf "$docker_cli" "$path_head/docker"
  echo "Linked docker into current shell PATH directory: $path_head/docker"
fi

echo "Docker CLI: $docker_cli"
echo "Open a new shell, or run: source \"$profile\""
