# Per-module migration guide
# Apply this pattern to any .py file that still uses sqlite3 directly
# (case_management.py, auth.py, routers/*.py, etc.)

# =============================================================
# CHANGE 1: imports  (top of file)
# =============================================================

# REMOVE:
import sqlite3

# ADD:
from backend.demo1.pg import get_conn


# =============================================================
# CHANGE 2: init_*_table() functions
# =============================================================

# REMOVE the entire function body — tables already exist in Supabase:

# BEFORE:
def init_cases_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS cases (...)")
    conn.commit()
    conn.close()

# AFTER (one-liner no-op):
def init_cases_table():
    pass   # table exists in Supabase


# =============================================================
# CHANGE 3: query pattern
# =============================================================

# BEFORE:
def get_cases(firm_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM cases WHERE firm_id = ? AND deleted = 0 ORDER BY created_at DESC",
        (firm_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# AFTER (RLS handles firm_id — no WHERE firm_id needed):
def get_cases(firm_id: str):
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT * FROM cases WHERE deleted = FALSE ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# =============================================================
# CHANGE 4: insert pattern
# =============================================================

# BEFORE:
def create_case(firm_id: str, case_number: str, client_name: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO cases (firm_id, case_number, client_name) VALUES (?, ?, ?)",
        (firm_id, case_number, client_name)
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id

# AFTER:
def create_case(firm_id: str, case_number: str, client_name: str):
    with get_conn(firm_id) as conn:
        cur = conn.execute(
            "INSERT INTO cases (firm_id, case_number, client_name) VALUES (%s, %s, %s) RETURNING id",
            (firm_id, case_number, client_name)
        )
        return cur.fetchone()["id"]


# =============================================================
# CHANGE 5: FastAPI route pattern (using db_dep)
# =============================================================

# BEFORE:
from fastapi import Depends
from backend.demo1.auth import get_current_firm_id

@router.get("/cases")
def list_cases(firm_id: str = Depends(get_current_firm_id)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM cases WHERE firm_id = ? AND deleted = 0",
        (firm_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# AFTER:
from fastapi import Depends
from backend.demo1.pg import db_dep
from backend.demo1.auth import get_current_firm_id

@router.get("/cases")
def list_cases(db=Depends(db_dep)):
    # firm_id is baked into the connection via RLS — no filter needed
    return db.execute(
        "SELECT * FROM cases WHERE deleted = FALSE ORDER BY created_at DESC"
    ).fetchall()


# =============================================================
# CHANGE 6: placeholder syntax  (already done by patch script)
# =============================================================

# SQLite uses ?    →    Postgres uses %s
# The apply_postgres_patch.sh script handles this automatically.
# If patching manually:
#   sed -i 's/(?<![%])\?/%s/g' your_file.py
# Or with perl (more reliable):
#   perl -i -pe 's/(?<!%)\?/%s/g' your_file.py


# =============================================================
# CHANGE 7: boolean columns
# =============================================================

# SQLite stores booleans as 0/1 integers.
# Postgres has native BOOLEAN. Update any comparisons:

# BEFORE:  WHERE deleted = 0
# AFTER:   WHERE deleted = FALSE

# BEFORE:  WHERE active = 1
# AFTER:   WHERE active = TRUE

# BEFORE:  VALUES (?, ?, 1, 0)     (active, deleted as ints)
# AFTER:   VALUES (%s, %s, TRUE, FALSE)


# =============================================================
# CHANGE 8: LIKE → ILIKE  (optional but recommended)
# =============================================================

# Postgres LIKE is case-sensitive. Use ILIKE for case-insensitive search:
# BEFORE:  WHERE name LIKE ?
# AFTER:   WHERE name ILIKE %s


# =============================================================
# CHANGE 9: lastrowid → RETURNING id
# =============================================================

# BEFORE:
cur = conn.execute("INSERT INTO ...", params)
new_id = cur.lastrowid

# AFTER:
cur = conn.execute("INSERT INTO ... RETURNING id", params)
new_id = cur.fetchone()["id"]
