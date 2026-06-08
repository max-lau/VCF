#!/usr/bin/env bash
# =============================================================
# ParaIQ — apply_postgres_patch.sh
# Run from: /root/nlp-portfolio
#
# What this does:
#   1. Copies pg.py and database.py into the backend
#   2. Replaces ? placeholders with %s in all SQL queries
#   3. Patches main.py startup to init the Postgres pool
#   4. Adds TenantMiddleware to main.py
# =============================================================

set -e
BACKEND="backend/demo1"
MAIN="$BACKEND/main.py"

echo "▶  Step 1: copy new pg.py and database.py"
cp pg.py     $BACKEND/pg.py
cp database.py $BACKEND/database.py
echo "  ✓ pg.py and database.py in place"

# =============================================================
# Step 2: replace ? placeholders with %s
# Only replaces ? that appear inside SQL strings — i.e. after
# keywords like VALUES, WHERE, SET, INSERT, UPDATE, LIMIT etc.
# Safe to run multiple times (idempotent if already %s).
# =============================================================
echo "▶  Step 2: replacing SQL ? placeholders with %s"

# Back up all .py files first
find $BACKEND -name "*.py" | while read f; do
    cp "$f" "${f}.bak"
done
echo "  ✓ backups written (*.py.bak)"

# Replace standalone ? not preceded by % (avoids double-replacing)
find $BACKEND -name "*.py" ! -name "pg.py" | xargs \
    sed -i 's/(?<![%])\?/%s/g' 2>/dev/null || \
    find $BACKEND -name "*.py" ! -name "pg.py" | xargs \
    perl -i -pe 's/(?<!%)\?/%s/g'

echo "  ✓ ? → %s replacement done"

# =============================================================
# Step 3: patch main.py — add pool init at startup
# =============================================================
echo "▶  Step 3: patching main.py startup"

# Add import at top (after existing imports block)
if ! grep -q "from backend.demo1.pg import" $MAIN; then
    # Insert after the last 'from backend' import line
    sed -i '/^from backend\.demo1/{ h; d }; /^[^f]/{ x; /^from backend\.demo1/{ p; s/.*/from backend.demo1.pg import init_pool, make_tenant_middleware/p } }; x' $MAIN 2>/dev/null || true

    # Simpler fallback: prepend to file after load_dotenv
    python3 - <<'PYEOF'
import re

path = "backend/demo1/main.py"
with open(path) as f:
    src = f.read()

pg_import = "from backend.demo1.pg import init_pool, make_tenant_middleware\n"
if pg_import.strip() not in src:
    # Add after load_dotenv() line
    src = src.replace(
        "load_dotenv()",
        "load_dotenv()\n" + pg_import
    )
    with open(path, "w") as f:
        f.write(src)
    print("  ✓ import added to main.py")
else:
    print("  ✓ import already present")
PYEOF
fi

# Add init_pool() call at app startup
python3 - <<'PYEOF'
path = "backend/demo1/main.py"
with open(path) as f:
    src = f.read()

startup_block = """
@app.on_event("startup")
async def _startup():
    init_pool()

"""

middleware_line = "app.add_middleware(make_tenant_middleware())\n"

if "init_pool()" not in src:
    # Insert before the first @app.include_router or @app.get
    import re
    src = re.sub(
        r'(app\.include_router|app\.add_middleware|@app\.)',
        startup_block + r'\1',
        src,
        count=1
    )
    print("  ✓ startup init_pool() added")
else:
    print("  ✓ init_pool() already present")

if "make_tenant_middleware" not in src:
    # Add middleware registration right after app = FastAPI(...)
    src = re.sub(
        r'(app\s*=\s*FastAPI\([^)]*\))',
        r'\1\n' + middleware_line,
        src
    )
    print("  ✓ TenantMiddleware registered")
else:
    print("  ✓ TenantMiddleware already present")

with open(path, "w") as f:
    f.write(src)
PYEOF

echo "  ✓ main.py patched"

# =============================================================
# Step 4: verify DATABASE_URL is in .env
# =============================================================
echo "▶  Step 4: checking .env"
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    if grep -q "DATABASE_URL" $ENV_FILE; then
        echo "  ✓ DATABASE_URL already in .env"
    else
        echo ""
        echo "  ⚠  Add this line to your .env file:"
        echo "  DATABASE_URL=postgresql://paraiq_app:PASSWORD@db.XXXX.supabase.co:5432/postgres"
        echo ""
    fi
else
    echo "  ⚠  No .env file found. Create one with:"
    echo "  DATABASE_URL=postgresql://paraiq_app:PASSWORD@db.XXXX.supabase.co:5432/postgres"
fi

echo ""
echo "============================================================"
echo "  ✅  Patch applied!"
echo "  Next: add DATABASE_URL to .env, then restart the server"
echo "  Test: curl http://localhost:8000/health"
echo "============================================================"
