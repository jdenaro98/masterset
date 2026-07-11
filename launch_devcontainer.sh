#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")" && pwd)"

if ! command -v devcontainer &>/dev/null; then
  echo "devcontainer CLI not found. Install it with:"
  echo "  npm install -g @devcontainers/cli"
  echo ""
  echo "Alternatively, open this folder in VS Code and choose"
  echo "'Reopen in Container' from the command palette."
  exit 1
fi

echo "Building and starting devcontainer…"
devcontainer up --workspace-folder "$WORKSPACE"

echo ""
echo "Container is ready. Dropping into a shell with 'npm run dev' wired up."
echo "Run:  npm run dev"
echo ""
devcontainer exec --workspace-folder "$WORKSPACE" bash
