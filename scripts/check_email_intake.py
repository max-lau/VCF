"""Check recent email intake and case_documents output."""
import os
from dotenv import load_dotenv
load_dotenv("/root/VCF/.env")
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("--- Recent email_processing_log entries ---")
cur.execute("""
    SELECT subject, processed_at, routing_decision, discard_reason
    FROM email_processing_log
    WHERE subject ILIKE '%%test%%'
    ORDER BY processed_at DESC LIMIT 10
""")
for row in cur.fetchall():
    print(row)

print("\n--- Recent case_documents ---")
cur.execute("""
    SELECT id, document_name, doc_text, doc_type, created_at
    FROM case_documents
    ORDER BY created_at DESC LIMIT 10
""")
for row in cur.fetchall():
    print(row[0], row[1], row[3], str(row[4]))
    print("TEXT:", (row[2] or "")[:200])
    print()

cur.close()
conn.close()
