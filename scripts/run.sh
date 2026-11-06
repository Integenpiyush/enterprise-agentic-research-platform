#!/usr/bin/env bash
set -euo pipefail
if [[ -f .venv/bin/activate ]]; then . .venv/bin/activate; fi
python data/seed_database.py
streamlit run app.py
