#!/usr/bin/env bash
set -e

# Run all Kali AI unit tests
cd "$(dirname "$0")/.."
python3 -m unittest discover tests -v "$@"
