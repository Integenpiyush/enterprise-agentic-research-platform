#!/usr/bin/env bash
set -euo pipefail
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp -n .env.example .env
python data/seed_database.py
