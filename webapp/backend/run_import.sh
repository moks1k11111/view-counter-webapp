#!/bin/bash

export DATABASE_URL="postgresql://viewcounter_38ir_user:KzYob6p8xN8ZL1akzA7mXgKhff1hwkvN@dpg-d4u18svgi27c73a9p1e0-a.frankfurt-postgres.render.com/viewcounter_38ir?sslmode=require"

export GOOGLE_SHEETS_CREDENTIALS_JSON="$(cat ../../credentials_base64.txt)"

python3 import_from_sheets.py
