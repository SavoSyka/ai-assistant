#!/bin/sh
set -e

python -c "from app.db import init_db; init_db()"

exec "$@"
