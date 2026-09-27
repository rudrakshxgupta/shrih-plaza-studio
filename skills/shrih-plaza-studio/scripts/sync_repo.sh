#!/usr/bin/env bash
# Fresh copy of the Shrih Plaza repo: live memory, real photos, logos.
set -e
REPO_URL="${SHRIH_REPO_URL:-https://github.com/rudrakshxgupta/shrih-plaza-studio}"
DEST="${SHRIH_REPO:-/home/claude/shrih-plaza-studio}"
rm -rf "$DEST"
GIT_TERMINAL_PROMPT=0 git clone --depth 1 -q "$REPO_URL" "$DEST" || {
  echo "CLONE FAILED: the repo is probably private. Ask the owner to make it public or upload the files."; exit 1; }
pip install -q Pillow --break-system-packages 2>/dev/null || true
cd "$DEST" && echo "synced $(git log -1 --format='%h %ad %s' --date=short)"
