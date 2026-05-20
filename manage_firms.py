"""
manage_firms.py — Create / wipe trial firms
Usage:
  python3 manage_firms.py create guest_trial
  python3 manage_firms.py wipe   guest_trial
"""
import sys, sqlite3, hashlib, os
from datetime import datetime, timezone

MAIN_DB  = '/root/nlp-portfolio/analyses.db'
AUTH_DB  = '/root/nlp-portfolio/backend/demo1/analyses.db'

def get_conn(db): 
    c = sqlite3.connect(db); c.row_factory = sqlite3.Row; return c

def create_firm(firm_id):
    print(f'Creating firm: {firm_id}')
    print('Done — invite users via Admin Panel > Invite User')
    print(f'Set firm_id = "{firm_id}" when inviting guests')
    print(f'\nTo wipe later: python3 manage_firms.py wipe {firm_id}')

def wipe_firm(firm_id):
    if firm_id in ('default',):
        print('ERROR: Cannot wipe default firm'); return

    # Wipe users from auth DB
    conn = get_conn(AUTH_DB)
    users = conn.execute('SELECT id FROM users WHERE firm_id=?', (firm_id,)).fetchall()
    user_ids = [u['id'] for u in users]
    conn.execute('DELETE FROM role_assignments WHERE user_id IN (' + ','.join('?'*len(user_ids)) + ')', user_ids)
    conn.execute('DELETE FROM users WHERE firm_id=?', (firm_id,))
    conn.commit(); conn.close()
    print(f'Deleted {len(user_ids)} users from firm {firm_id}')

    # Wipe cases and related data from main DB
    conn = get_conn(MAIN_DB)
    cases = conn.execute('SELECT id FROM cases WHERE firm_id=?', (firm_id,)).fetchall()
    case_ids = [c['id'] for c in cases]
    if case_ids:
        ph = ','.join('?'*len(case_ids))
        conn.execute(f'DELETE FROM case_documents WHERE case_id IN ({ph})', case_ids)
        conn.execute(f'DELETE FROM case_notes    WHERE case_id IN ({ph})', case_ids)
        conn.execute(f'DELETE FROM case_tags     WHERE case_id IN ({ph})', case_ids)
        conn.execute(f'DELETE FROM case_briefs   WHERE case_id IN ({ph})', case_ids)
        conn.execute(f'DELETE FROM case_contradictions WHERE case_id IN ({ph})', case_ids)
    conn.execute('DELETE FROM cases WHERE firm_id=?', (firm_id,))
    conn.commit(); conn.close()
    print(f'Deleted {len(case_ids)} cases and all related data for firm {firm_id}')
    print('Wipe complete ✓')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd, firm = sys.argv[1], sys.argv[2]
    if cmd == 'create': create_firm(firm)
    elif cmd == 'wipe':  wipe_firm(firm)
    else: print(f'Unknown command: {cmd}')
