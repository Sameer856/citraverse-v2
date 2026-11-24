#!/bin/zsh
set -e
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python || ! -f build/libcitra_ch347.dylib ]]; then
  echo "Run Setup Mac.command first."
  read -r
  exit 1
fi
.venv/bin/python app.py
