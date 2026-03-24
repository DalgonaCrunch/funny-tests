#!/bin/bash

cd "$(dirname "$0")"

source .venv/bin/activate
export TELEGRAM_BOT_TOKEN=$(cat .token)

claude \
  --channels plugin:telegram@claude-plugins-official \
  --verbose \
  --dangerously-skip-permissions
