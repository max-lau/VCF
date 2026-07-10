# WaW Demo — Rollback Guide

Everything below was added on 2026-07-08 solely to make the 8 WaW demo documents
clickable in the Documents tab for a prospect pitch. Nothing here touches any other
firm's data or behavior. Run these steps **after** the WaW demo is done to fully
restore ParaIQ to its pre-demo state.

There are two independent things to roll back:
  A) The document-serving patch (Nginx + Vue) — Steps 1–4 below.
  B) The WaW tenant's seeded data itself (firm, user, 8 cases, notes, kanban cards,
     documents) — Step 5 below. Skip this if you want to keep the demo tenant
     around for future pitches; only do it if you want WaW fully gone.

---

## A) Roll back the document-serving patch

### Step 1 — Revert the Vue component

The patch wrapped one `<td>` in `MatterDetailView.vue` with a conditional link.
Cleanest revert is restoring from git if the repo is clean, otherwise a scripted
reverse-patch:

```bash
cd /root/nlp-portfolio
git diff --stat frontend/paraiq-vue/src/views/matters/MatterDetailView.vue
# if that shows only this one change, the simplest revert is:
git checkout -- frontend/paraiq-vue/src/views/matters/MatterDetailView.vue
```

**If the file has other uncommitted changes** (so a blind `git checkout` would lose
them), use this instead — it removes exactly the block we added and nothing else:

```bash
python3 - <<'PY'
path = "frontend/paraiq-vue/src/views/matters/MatterDetailView.vue"
with open(path, encoding="utf-8") as f:
    content = f.read()

NEW = '''<td class="doc-name">
                  <!-- WAW DEMO — TEMPORARY: linkify only the known WaW demo filenames.
                       Remove this v-if/v-else pair and restore the single line above
                       after the prospect demo — see WAW_DEMO_ROLLBACK.md -->
                  <a v-if="(d.document_name || '').match(/^(chen_weiming|krystyna_nowak)_/)"
                     :href="`/demo-files/${d.document_name}`"
                     target="_blank" rel="noopener">{{ d.document_name || d.original_filename || d.filename }}</a>
                  <span v-else>{{ d.document_name || d.original_filename || d.filename }}</span>
                </td>'''
OLD = '<td class="doc-name">{{ d.document_name || d.original_filename || d.filename }}</td>'

count = content.count(NEW)
print(f"Found {count} occurrence(s) of the WAW DEMO block.")
if count != 1:
    print("ABORTING — expected exactly 1 occurrence, found", count, "- no changes made.")
else:
    content = content.replace(NEW, OLD)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Reverted successfully.")
PY
```

### Step 2 — Rebuild the frontend

```bash
cd /root/nlp-portfolio/frontend
cp -r dist-vue dist-vue.bak-pre-rollback   # safety net, same pattern as before
cd paraiq-vue
free -h        # sanity check memory headroom before building, same as last time
npm run build
```

Confirm `MatterDetailView-*.js` gets a new hash in the build output (proof it actually
recompiled), then spot-check `dist-vue/index.html` timestamp is fresh.

### Step 3 — Remove the Nginx location block

```bash
cp /etc/nginx/sites-enabled/paraiq /etc/nginx/sites-enabled/paraiq.bak-pre-rollback
python3 - <<'PY'
path = "/etc/nginx/sites-enabled/paraiq"
with open(path, encoding="utf-8") as f:
    content = f.read()

BLOCK = '''    # ===== WAW DEMO — TEMPORARY, added 2026-07-08 =====
    # Serves only the 8 WaW demo client documents. Remove this whole block
    # (and rmdir the public_files/ dir) after the prospect demo — see
    # WAW_DEMO_ROLLBACK.md for the exact revert steps.
    location ^~ /demo-files/ {
        alias /root/nlp-portfolio/demo_docs/waw/public_files/;
        autoindex off;
        add_header Cache-Control "no-store";
    }
    # ===== END WAW DEMO =====

'''

count = content.count(BLOCK)
print(f"Found {count} occurrence(s) of the WAW DEMO nginx block.")
if count != 1:
    print("ABORTING — expected exactly 1 occurrence, found", count, "- no changes made.")
else:
    content = content.replace(BLOCK, "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Reverted successfully.")
PY
nginx -t && systemctl reload nginx
```

Confirm the block is gone and the site still loads normally:

```bash
curl -I http://localhost/demo-files/chen_weiming_intake_questionnaire_zh.png
```

Should now return `404` (or fall through to the SPA and return the `index.html`
content-type) rather than `200` with `image/png` — that's the expected, correct
post-rollback state.

### Step 4 — Remove the exposed files directory

```bash
rm -rf /root/nlp-portfolio/demo_docs/waw/public_files
```

The original 8 files still exist untouched in `/root/nlp-portfolio/demo_docs/waw/`
(outside `public_files/`) — this only removes the web-exposed copies.

### Cleanup the backup files once you've confirmed everything works:

```bash
rm /etc/nginx/sites-enabled/paraiq.bak-pre-waw-demo
rm -rf /root/nlp-portfolio/frontend/dist-vue.bak-pre-waw-demo
rm -rf /root/nlp-portfolio/frontend/dist-vue.bak-pre-rollback
```

(Keep `paraiq.bak-pre-rollback` briefly in case the Nginx revert needs a redo —
delete once confirmed stable.)

---

## B) Roll back the seeded WaW tenant data (optional)

Only do this if you want the WaW firm, user, and all 8 cases fully removed from the
database — e.g. once you've either signed WaW as a real client (in which case you'd
want to convert this demo data to something else entirely, not just delete it) or
decided not to pursue them further.

```bash
cd /root/nlp-portfolio
source .venv/bin/activate
export DATABASE_URL="$(grep '^DATABASE_URL' .env | cut -d= -f2-)"
python3 demo_docs/waw/seed_waw.py --reset --dry-run   # preview what would be deleted
python3 -c "
import argparse, sys
sys.argv = ['x', '--reset']
"
# then, once you're sure:
python3 - <<'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SET app.current_firm_id = 'waw'")
for t in ['kanban_cards', 'case_documents', 'case_notes']:
    cur.execute(f"DELETE FROM {t} WHERE firm_id = 'waw'")
    print(t, cur.rowcount, "rows deleted")
cur.execute("DELETE FROM cases WHERE firm_id = 'waw'")
print("cases", cur.rowcount, "rows deleted")
cur.execute("DELETE FROM public.users WHERE firm_id = 'waw'")
print("users", cur.rowcount, "rows deleted")
cur.execute("DELETE FROM firms WHERE id = 'waw'")
print("firms", cur.rowcount, "rows deleted")
conn.commit()
print("Committed.")
PY
```

(Note: `seed_waw.py --reset` alone re-seeds after wiping — use the raw DELETE block
above, or run `--reset` and simply don't follow it with the seed step, i.e. answer
"no" mentally to re-seeding and just Ctrl-C after the reset prints "cleared existing
waw rows" but before it proceeds to re-insert. The explicit DELETE block above is
cleaner if you just want it gone for good.)

Verify:
```bash
python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT count(*) FROM firms WHERE id='waw'\")
print('firms remaining:', cur.fetchone())
"
```
Expect `(0,)`.

---

## Quick reference — what changed, where

| Layer | File | What | Reversible via |
|---|---|---|---|
| Data | Postgres | firm, user, 8 cases, 87 notes, 87 kanban cards, 8 documents | Section B above |
| Files | `/root/nlp-portfolio/demo_docs/waw/public_files/` | 8 client files exposed for web serving | Step 4 |
| Web server | `/etc/nginx/sites-enabled/paraiq` | `/demo-files/` location block | Step 3 |
| Frontend | `MatterDetailView.vue` | conditional document link | Step 1 + rebuild (Step 2) |

Total rollback time: ~10 minutes, most of it the Vite rebuild.
