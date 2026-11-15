#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../android-template"
gradle wrapper --gradle-version 9.5.0 --distribution-type bin
