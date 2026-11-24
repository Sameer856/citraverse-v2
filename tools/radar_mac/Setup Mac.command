#!/bin/zsh
set -e
cd -- "${0:A:h}"
python3 setup_mac.py
echo "Press Return to close."
read -r
