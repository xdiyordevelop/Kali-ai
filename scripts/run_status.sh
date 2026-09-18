#!/usr/bin/env bash
set -e

# Run Kali AI diagnostic status
cd "$(dirname "$0")/.."
python3 -m kali_ai status "$@"
