"""
seed_demo.py — Create ParaIQ demo account with realistic pre-seeded data
Run from: cd /root/nlp-portfolio && python3 seed_demo.py
"""
import os, sys, sqlite3, json
from datetime import datetime, timezone

os.chdir('/root/nlp-portfolio')
sys.path.insert(0, '/root/nlp-portfolio')
os.environ['TESTING'] = '1'

from dotenv import load_dotenv
load_dotenv('/root/nlp-portfolio/.env')

from backend.demo1.auth import hash_password

DB       = 'backend/demo1/analyses.db'
FIRM_ID  = 'meridian_legal'
EMAIL    = 'demo@paraiq.com'
USERNAME = 'demo'
PASSWORD = 'ParaIQ2026!'
NOW      = datetime.now(timezone.utc).isoformat()

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c

# ── 1. Init case tables ────────────────────────────────────────────────────────
db = conn()
db.executescript("""
CREATE TABLE IF NOT EXISTS cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number   TEXT UNIQUE NOT NULL,
    client_name   TEXT NOT NULL,
    matter_number TEXT,
    status        TEXT DEFAULT 'open',
    court         TEXT,
    judge         TEXT,
    filing_date   TEXT,
    description   TEXT,
    risk_level    TEXT DEFAULT 'unknown',
    firm_id       TEXT DEFAULT 'default',
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now')),
    deleted       INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS case_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id       INTEGER NOT NULL REFERENCES cases(id),
    document_name TEXT NOT NULL,
    source        TEXT DEFAULT 'uploaded',
    doc_text      TEXT,
    sentiment     TEXT,
    risk_score    REAL,
    events_json   TEXT,
    entities_json TEXT,
    summary       TEXT,
    language      TEXT DEFAULT 'en',
    upload_date   TEXT DEFAULT (datetime('now')),
    pacer_doc_id  TEXT,
    pacer_seq_no  TEXT
);
CREATE TABLE IF NOT EXISTS case_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id    INTEGER NOT NULL REFERENCES cases(id),
    author     TEXT DEFAULT 'System',
    note       TEXT NOT NULL,
    pinned     INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS case_tags (
    case_id INTEGER NOT NULL REFERENCES cases(id),
    tag     TEXT NOT NULL,
    PRIMARY KEY (case_id, tag)
);
""")
db.commit()

# Add firm_id column if missing (for existing tables)
try:
    db.execute("ALTER TABLE cases ADD COLUMN firm_id TEXT DEFAULT 'default'")
    db.commit()
except:
    pass

print("✓ Case tables initialized")

# ── 2. Clean up previous demo data ─────────────────────────────────────────────
old = db.execute("SELECT id FROM users WHERE email=?", (EMAIL,)).fetchone()
if old:
    db.execute("DELETE FROM role_assignments WHERE user_id=?", (old['id'],))
    db.execute("DELETE FROM users WHERE id=?", (old['id'],))

db.execute("DELETE FROM case_tags     WHERE case_id IN (SELECT id FROM cases WHERE firm_id=?)", (FIRM_ID,))
db.execute("DELETE FROM case_notes    WHERE case_id IN (SELECT id FROM cases WHERE firm_id=?)", (FIRM_ID,))
db.execute("DELETE FROM case_documents WHERE case_id IN (SELECT id FROM cases WHERE firm_id=?)", (FIRM_ID,))
db.execute("DELETE FROM cases         WHERE firm_id=?", (FIRM_ID,))
db.execute("DELETE FROM depositions   WHERE case_number LIKE 'MLG-2026-%'")
db.execute("DELETE FROM motions       WHERE case_number LIKE 'MLG-2026-%'")
db.execute("DELETE FROM contracts     WHERE case_number LIKE 'MLG-2026-%'")
db.execute("DELETE FROM discovery_files WHERE case_number LIKE 'MLG-2026-%'")
db.commit()
print("✓ Previous demo data cleared")

# ── 3. Create demo user ────────────────────────────────────────────────────────
cur = db.execute("""
    INSERT INTO users (username, email, password_hash, role, active, created_at, firm_id, plan)
    VALUES (?, ?, ?, 'firm_admin', 1, ?, ?, 'professional')
""", (USERNAME, EMAIL, hash_password(PASSWORD), NOW, FIRM_ID))
user_id = cur.lastrowid
db.execute("""
    INSERT INTO role_assignments (user_id, role_id, firm_id, assigned_at)
    VALUES (?, 2, ?, ?)
""", (user_id, FIRM_ID, NOW))
db.commit()
print(f"✓ Demo user: {EMAIL} / {PASSWORD}")

# ── 4. Seed cases ──────────────────────────────────────────────────────────────
CASES = [
    dict(
        case_number   = 'MLG-2026-001',
        client_name   = 'Hartwell Industries LLC',
        matter_number = 'M-4821',
        status        = 'open',
        court         = 'Superior Court of California, Los Angeles County',
        judge         = 'Hon. Patricia M. Chen',
        filing_date   = '2026-01-15',
        risk_level    = 'high',
        firm_id       = FIRM_ID,
        description   = 'Breach of contract dispute arising from a $4.2M commercial construction project. Client alleges defective workmanship, substandard materials, and failure to complete on schedule. Opposing counsel: Davis & Thornton LLP.',
        notes = [
            ('Senior Partner A. Reid', 'Initial intake complete. Client provided full contract documentation and photographic evidence of construction defects. Retainer received $25,000.', 1),
            ('Associate J. Kim', 'Reviewed Amendment #2 — 60-day extension granted but completion still missed. Strong breach of §7.3 Completion Guarantee.', 0),
            ('System', 'Deposition of Robert Hartwell scheduled May 28, 2026.', 0),
        ],
        tags = ['breach-of-contract', 'construction', 'commercial', 'high-value'],
        docs = [
            dict(document_name='Construction Agreement Phase II — Executed.pdf', source='uploaded',
                 doc_text='This Commercial Construction Agreement is entered into as of March 1, 2025, between Hartwell Industries LLC ("Owner") and Meridian Construction Co. ("Contractor"). The total contract price shall be $4,200,000 for the complete construction of Phase II improvements. Section 7.3 Completion Guarantee: Contractor warrants that all work shall be substantially complete by December 31, 2025.',
                 sentiment='neutral', risk_score=0.72,
                 entities_json=json.dumps([{'text':'$4,200,000','type':'MONEY'},{'text':'December 31, 2025','type':'DATE'},{'text':'Section 7.3','type':'CLAUSE'}]),
                 summary='Primary construction contract. Fixed price $4.2M. Completion deadline December 31, 2025. §7.3 completion guarantee is the key clause at issue.'),
            dict(document_name='Email Chain — Defect Notice November 2025.pdf', source='uploaded',
                 doc_text='From: Robert Hartwell <r.hartwell@hartwellindustries.com> To: Project Manager, Meridian Construction. Subject: FORMAL NOTICE OF DEFECTS — CURE DEMANDED. Dear Sir: This letter constitutes formal written notice of material defects in the foundation work completed to date. You are hereby notified that you have 30 days to cure all identified defects or we will exercise our rights under the contract.',
                 sentiment='negative', risk_score=0.81,
                 entities_json=json.dumps([{'text':'Robert Hartwell','type':'PERSON'},{'text':'30 days','type':'DURATION'},{'text':'Meridian Construction','type':'ORG'}]),
                 summary='Formal defect notice establishing the 30-day cure period. Critical document for establishing breach timeline.'),
            dict(document_name='Structural Inspection Report — December 2025.pdf', source='uploaded',
                 doc_text='ENGINEERING INSPECTION REPORT — Prepared by: Pacific Engineering Group LLC. Subject property: Hartwell Phase II Construction Site. Finding 1: Foundation rebar spacing does not meet specified 12-inch centers — actual spacing measured at 18-24 inches in multiple locations. Finding 2: Concrete compressive strength test results show 22% of samples below minimum 4,000 PSI specification. CONCLUSION: Work does not conform to contract specifications.',
                 sentiment='negative', risk_score=0.91,
                 entities_json=json.dumps([{'text':'Pacific Engineering Group LLC','type':'ORG'},{'text':'4,000 PSI','type':'SPEC'},{'text':'22%','type':'METRIC'}]),
                 summary='Third-party engineering report confirming substandard materials and non-conforming construction. Strong evidentiary document for defect claims.'),
        ]
    ),
    dict(
        case_number   = 'MLG-2026-002',
        client_name   = 'Chen Family Trust',
        matter_number = 'M-4836',
        status        = 'pending',
        court         = 'Probate Court, San Francisco County',
        judge         = 'Hon. Robert J. Williams',
        filing_date   = '2026-02-03',
        risk_level    = 'low',
        firm_id       = FIRM_ID,
        description   = 'Administration of the Chen Family Trust following the passing of Dr. James Chen on January 18, 2026. Estate valued at approximately $12.8M including San Francisco real property, brokerage accounts, and 40% interest in Chen Medical Group LLC.',
        notes = [
            ('Senior Partner A. Reid', 'Court appointed Jennifer Chen as successor trustee March 20, 2026. First accounting due August 2026. No contested claims to date.', 1),
            ('Associate M. Torres', 'Real property appraisals ordered for SF residence and Napa vacation property. Brokerage accounts frozen pending court order.', 0),
        ],
        tags = ['estate', 'probate', 'trust-administration', 'high-value'],
        docs = [
            dict(document_name='Chen Family Trust Agreement — Restated 2021.pdf', source='uploaded',
                 doc_text='THE CHEN FAMILY REVOCABLE TRUST — Restated and Amended December 15, 2021. Settlors: Dr. James Chen and Margaret Chen. Upon the death of the surviving settlor, the trust shall become irrevocable. Article IV Distribution: The trustee shall distribute the residuary estate in equal shares to the Settlors\' children: Jennifer Chen, Michael Chen, and David Chen. Article VI: Trustee powers include authority to sell, lease, or encumber trust property without court approval.',
                 sentiment='neutral', risk_score=0.12,
                 entities_json=json.dumps([{'text':'Dr. James Chen','type':'PERSON'},{'text':'Margaret Chen','type':'PERSON'},{'text':'Jennifer Chen','type':'PERSON'},{'text':'December 15, 2021','type':'DATE'}]),
                 summary='Primary trust instrument. Equal distribution to three children. Successor trustee: Jennifer Chen.'),
        ]
    ),
    dict(
        case_number   = 'MLG-2026-003',
        client_name   = 'TechVenture LLC',
        matter_number = 'M-4849',
        status        = 'open',
        court         = 'U.S. District Court, Northern District of California',
        judge         = 'Hon. Sarah K. Patel',
        filing_date   = '2026-03-11',
        risk_level    = 'high',
        firm_id       = FIRM_ID,
        description   = 'Trade secret misappropriation and breach of NDA. Former VP of Engineering Marcus Chen allegedly exfiltrated proprietary AI model architecture prior to departure, now deployed at competitor DataStream Inc. Preliminary injunction granted April 1, 2026.',
        notes = [
            ('Senior Partner A. Reid', 'Preliminary injunction GRANTED April 1, 2026. DataStream prohibited from commercializing any AI models developed March–December 2025. Major early win.', 1),
            ('Associate J. Kim', 'Forensic expert Dr. Sarah Patel (unrelated to judge) confirmed 847 repository accesses and 4.2GB download in final 30 days of employment. Report attached.', 0),
            ('System', 'Discovery phase opened. Opposing counsel Morrison & Foerster issued broad document requests. Response due June 15, 2026.', 0),
        ],
        tags = ['trade-secret', 'IP', 'federal', 'injunction-granted', 'tech'],
        docs = [
            dict(document_name='TechVenture NDA — Marcus Chen — Executed 2022.pdf', source='uploaded',
                 doc_text='NON-DISCLOSURE AND INTELLECTUAL PROPERTY ASSIGNMENT AGREEMENT. This Agreement is entered into June 15, 2022, between TechVenture LLC and Marcus Chen ("Employee"). Section 4.2 IP Assignment: Employee assigns to Company all inventions, developments, and trade secrets conceived during employment, including work performed on personal equipment or outside business hours. Section 8 Non-Competition: Employee agrees not to work for a direct competitor for 12 months following termination.',
                 sentiment='neutral', risk_score=0.45,
                 entities_json=json.dumps([{'text':'Marcus Chen','type':'PERSON'},{'text':'TechVenture LLC','type':'ORG'},{'text':'June 15, 2022','type':'DATE'},{'text':'Section 4.2','type':'CLAUSE'},{'text':'12 months','type':'DURATION'}]),
                 summary='NDA with broad IP assignment clause. §4.2 covers work on personal equipment. Non-compete likely unenforceable under CA law but NDA remains valid.'),
            dict(document_name='Forensic Report — Repository Access Log Analysis.pdf', source='uploaded',
                 doc_text='CONFIDENTIAL — ATTORNEY WORK PRODUCT. Forensic Analysis by Dr. Sarah Patel, PhD (Computer Science). Subject: Repository access patterns of Marcus Chen, January–March 2026. FINDINGS: Defendant accessed proprietary neural architecture repository 847 times in 30 days preceding resignation. Total data downloaded: 4.2GB comprising 23 core model checkpoint files. Access timestamps show 67% of downloads occurred between 11pm–4am — outside normal working hours. Within 61 days of joining DataStream Inc., company filed 3 patent applications with substantially similar transformer architecture specifications.',
                 sentiment='neutral', risk_score=0.94,
                 entities_json=json.dumps([{'text':'Marcus Chen','type':'PERSON'},{'text':'847 times','type':'METRIC'},{'text':'4.2GB','type':'METRIC'},{'text':'DataStream Inc.','type':'ORG'},{'text':'3 patent applications','type':'LEGAL'}]),
                 summary='Forensic evidence of systematic pre-departure exfiltration. 847 accesses, 4.2GB downloaded, 67% outside business hours. Strongest document in case.',
                 pacer_doc_id='2026CV03892-047'),
        ]
    ),
]

case_id_map = {}
for c in CASES:
    notes = c.pop('notes')
    tags  = c.pop('tags')
    docs  = c.pop('docs')

    cur = db.execute("""
        INSERT INTO cases
          (case_number, client_name, matter_number, status, court, judge,
           filing_date, description, risk_level, firm_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (c['case_number'], c['client_name'], c['matter_number'], c['status'],
          c['court'], c['judge'], c['filing_date'], c['description'],
          c['risk_level'], c['firm_id']))
    cid = cur.lastrowid
    case_id_map[c['case_number']] = cid

    for author, note, pinned in notes:
        db.execute("INSERT INTO case_notes (case_id, author, note, pinned) VALUES (?,?,?,?)",
                   (cid, author, note, pinned))

    for tag in tags:
        db.execute("INSERT INTO case_tags (case_id, tag) VALUES (?,?)", (cid, tag))

    for d in docs:
        db.execute("""
            INSERT INTO case_documents
              (case_id, document_name, source, doc_text, sentiment, risk_score,
               entities_json, summary, language, pacer_doc_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (cid, d['document_name'], d['source'], d['doc_text'],
              d['sentiment'], d['risk_score'], d.get('entities_json'),
              d['summary'], d.get('language','en'), d.get('pacer_doc_id')))

    print(f"✓ Case {c['case_number']} — {c['client_name']} ({len(docs)} docs, {len(notes)} notes, {len(tags)} tags)")

db.commit()

# ── 5. Depositions ─────────────────────────────────────────────────────────────
DEPOS = [
    ('MLG-2026-001', 'Robert Hartwell', 'Plaintiff / CEO, Hartwell Industries LLC',
     '2026-05-28', 'Meridian Legal Group, 350 California St Suite 800, San Francisco CA', 'scheduled',
     'Key plaintiff witness. Prepare exhibits: original contract, Amendment #2, defect notice emails, inspection report. Focus on timeline expectations and communications with Meridian Construction project manager. Anticipated 4-hour deposition.'),
    ('MLG-2026-001', 'Derek Walsh', 'Project Manager, Meridian Construction Co.',
     '2026-06-12', 'Davis & Thornton LLP, 555 S. Flower St, Los Angeles CA', 'scheduled',
     'Defense witness. Depose on internal quality control procedures, material sourcing decisions, and knowledge of defects prior to the November cure notice. Request all internal inspection records before deposition.'),
    ('MLG-2026-003', 'Marcus Chen', 'Former VP Engineering, TechVenture LLC / Defendant',
     '2026-06-10', 'Zoom — Remote Deposition (JAMS Platform)', 'scheduled',
     'Central defendant. Focus: NDA awareness at signing, access logs explanation, timeline of departure, role at DataStream. Coordinate with forensic expert Dr. Patel. Prepare demonstrative exhibits of repository access timestamps.'),
]

for d in DEPOS:
    db.execute("""
        INSERT INTO depositions (case_number, witness_name, witness_role, depo_date, location, status, notes)
        VALUES (?,?,?,?,?,?,?)
    """, d)
    print(f"✓ Deposition: {d[1]} ({d[0]})")

# ── 6. Motions ─────────────────────────────────────────────────────────────────
MOTIONS = [
    ('MLG-2026-001', 'Motion to Compel Production of Internal Quality Inspection Reports',
     'Discovery Motion', '2026-04-22', '2026-06-05', 'filed',
     'Opposing counsel withheld 47 internal QC reports citing proprietary business information. Motion argues these are directly relevant to defect claims and not privileged. Supporting brief filed. Expecting favorable ruling based on similar precedent in Donovan v. Prestwood (2024).'),
    ('MLG-2026-003', 'Motion for Preliminary Injunction — Trade Secret Protection',
     'Emergency Motion', '2026-03-15', '2026-04-01', 'granted',
     'GRANTED April 1, 2026. Court found substantial likelihood of success on merits given forensic evidence. DataStream Inc. prohibited from using, deploying, or commercializing any AI models incorporating TechVenture proprietary architecture. Bond set at $500,000.'),
    ('MLG-2026-003', 'Motion to Compel Forensic Inspection of DataStream AI Systems',
     'Discovery Motion', '2026-05-01', '2026-06-20', 'filed',
     'Seeking court-appointed neutral forensic examiner to inspect DataStream AI systems for evidence of misappropriated code. DataStream resisting. Motion argues inspection is necessary and proportionate given $40M+ damages at stake.'),
    ('MLG-2026-002', 'Petition for Formal Probate Administration',
     'Probate Petition', '2026-02-10', '2026-03-20', 'granted',
     'GRANTED March 20, 2026. Jennifer Chen appointed successor trustee. Letters of administration issued. First accounting due August 31, 2026. No objections filed by beneficiaries.'),
]

for m in MOTIONS:
    db.execute("""
        INSERT INTO motions (case_number, title, motion_type, filed_date, hearing_date, status, notes)
        VALUES (?,?,?,?,?,?,?)
    """, m)
    print(f"✓ Motion: {m[1][:55]}...")

# ── 7. Contracts ───────────────────────────────────────────────────────────────
CONTRACTS = [
    ('MLG-2026-001', 'Commercial Construction Agreement Phase II — Executed',
     'Construction Contract', 'Hartwell Industries LLC / Meridian Construction Co.',
     '2025-03-01', '2025-12-31', 'disputed',
     'Primary contract at issue. $4.2M fixed-price. Key clauses: §7.3 Completion Guarantee, §12.1 Defect Liability Period (1 year), §15.4 Arbitration clause (client prefers litigation — research enforceability). Amendment #2 July 2025 extended completion by 60 days.'),
    ('MLG-2026-001', 'Construction Contract Amendment #2 — Schedule Extension',
     'Contract Amendment', 'Hartwell Industries LLC / Meridian Construction Co.',
     '2025-07-15', '2026-02-28', 'disputed',
     'Extends completion deadline by 60 days to February 28, 2026 in exchange for $85,000 reduction in retainage. Defendant argues this waived the original completion guarantee — client disputes this interpretation. Critical document for damages calculation.'),
    ('MLG-2026-003', 'Employee NDA and IP Assignment Agreement — Marcus Chen',
     'Employment Agreement', 'TechVenture LLC / Marcus Chen',
     '2022-06-15', '2025-06-15', 'active',
     'NDA and IP assignment. §4.2 broad IP assignment covers personal equipment. §8 Non-compete (12 months) likely unenforceable under CA Labor Code §16600 but NDA protection remains strong. Agreement survives termination per §11.'),
]

for c in CONTRACTS:
    db.execute("""
        INSERT INTO contracts (case_number, contract_name, contract_type, parties,
                               execution_date, expiry_date, status, notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, c)
    print(f"✓ Contract: {c[1][:55]}...")

# ── 8. NLP Analyses ────────────────────────────────────────────────────────────
ANALYSES = [
    dict(
        text='The contractor failed to complete the structural reinforcement work by the agreed deadline of December 31, 2025, resulting in significant financial damages to the plaintiff. Multiple inspections revealed substandard materials were used in the foundation work, violating Section 7.3 of the construction agreement. The defendant was notified in writing on November 15, 2025 but failed to cure the defects within the 30-day cure period specified in Section 12.1.',
        sentiment='negative', score=-0.76, tone='formal/legal', word_count=81,
        entities=json.dumps([
            {'text':'December 31, 2025','type':'DATE','relevance':0.95},
            {'text':'Section 7.3','type':'LEGAL_CLAUSE','relevance':0.93},
            {'text':'November 15, 2025','type':'DATE','relevance':0.88},
            {'text':'Section 12.1','type':'LEGAL_CLAUSE','relevance':0.87},
            {'text':'30-day cure period','type':'LEGAL_TERM','relevance':0.85},
        ]),
        keywords=json.dumps(['breach of contract','construction defect','cure period','substandard materials','financial damages']),
        summary='Document establishes contractor breach via missed deadline, substandard materials, and failure to cure within the 30-day contractual remedy period. Strong breach of §7.3 and §12.1.',
    ),
    dict(
        text='CONFIDENTIAL — ATTORNEY WORK PRODUCT. Forensic analysis confirms that defendant Marcus Chen accessed TechVenture\'s proprietary neural architecture repository 847 times in the 30 days preceding his resignation. Access logs confirm downloads of 23 core model checkpoint files totaling 4.2GB. Notably, 67% of download activity occurred between 11:00 PM and 4:00 AM, outside normal business hours. Within 61 days of joining DataStream Inc., the company filed three patent applications incorporating substantially similar transformer architecture specifications to those contained in the downloaded files.',
        sentiment='neutral', score=-0.18, tone='forensic/analytical', word_count=101,
        entities=json.dumps([
            {'text':'Marcus Chen','type':'PERSON','relevance':0.98},
            {'text':'TechVenture','type':'ORGANIZATION','relevance':0.97},
            {'text':'DataStream Inc.','type':'ORGANIZATION','relevance':0.95},
            {'text':'847 times','type':'METRIC','relevance':0.93},
            {'text':'4.2GB','type':'METRIC','relevance':0.90},
            {'text':'61 days','type':'DURATION','relevance':0.88},
        ]),
        keywords=json.dumps(['trade secret','misappropriation','access logs','neural architecture','patent applications','attorney work product','forensic analysis']),
        summary='Forensic analysis documents systematic pre-departure exfiltration: 847 accesses, 4.2GB downloaded primarily after hours. Rapid commercialization by DataStream within 61 days strongly supports misappropriation claim.',
    ),
]

for a in ANALYSES:
    db.execute("""
        INSERT INTO analyses (created_at, text, word_count, sentiment, score, tone, entities, keywords, summary)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (NOW, a['text'], a['word_count'], a['sentiment'], a['score'], a['tone'],
          a['entities'], a['keywords'], a['summary']))
    print(f"✓ NLP Analysis: {a['summary'][:60]}...")

# ── 9. Discovery files ─────────────────────────────────────────────────────────
DISC = [
    ('construction_contract_phase2.pdf','Construction Agreement Phase II — Executed.pdf',
     'a3f8c2d1e4b9f7a2',285000,'application/pdf','/uploads/discovery/MLG-2026-001/','MLG-2026-001','2025-03-01','reviewed',0,None,0.0,0),
    ('email_chain_defect_notice.pdf','Email Chain — Formal Defect Notice Nov 2025.pdf',
     'b7e1d4f2a8c3e6b9',127400,'application/pdf','/uploads/discovery/MLG-2026-001/','MLG-2026-001','2025-11-15','reviewed',0,None,0.0,0),
    ('structural_inspection_report.pdf','Structural Inspection Report — Pacific Engineering Group.pdf',
     'c2f5a8d1e4b7c3f6',341200,'application/pdf','/uploads/discovery/MLG-2026-001/','MLG-2026-001','2025-12-10','reviewed',0,None,0.0,0),
    ('techventure_nda_executed.pdf','TechVenture NDA — Marcus Chen — Executed 2022.pdf',
     'd9e2f5a1c8b4d7e3',94800,'application/pdf','/uploads/discovery/MLG-2026-003/','MLG-2026-003','2022-06-15','reviewed',0,None,0.0,0),
    ('forensic_access_log_report.pdf','Forensic Report — Repository Access Log Analysis.pdf',
     'e4f7a2d5b8e1c4f7',412900,'application/pdf','/uploads/discovery/MLG-2026-003/','MLG-2026-003','2026-04-10','reviewed',1,'Attorney Work Product',0.94,0),
    ('datastream_patent_applications.pdf','DataStream Inc. — Patent Applications Filed 2026.pdf',
     'f1b4e7a3d6c9f2b5',228300,'application/pdf','/uploads/discovery/MLG-2026-003/','MLG-2026-003','2026-05-01','reviewed',0,None,0.0,0),
]

for d in DISC:
    db.execute("""
        INSERT INTO discovery_files
          (filename, original_name, file_hash, file_size, mime_type, route,
           case_number, doc_date, status, privilege_flag, privilege_type,
           privilege_confidence, requires_review, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (*d, NOW))
    print(f"✓ Discovery: {d[1][:55]}...")

db.commit()
db.close()

print(f"""
{'='*62}
  DEMO ACCOUNT READY — ParaIQ
{'='*62}
  URL:      https://app.para-iq.com
  Email:    {EMAIL}
  Password: {PASSWORD}
  Role:     firm_admin · Meridian Legal Group

  Cases seeded:
  · MLG-2026-001  Hartwell Industries LLC          [HIGH RISK]
                  Breach of Contract — $4.2M construction dispute
  · MLG-2026-002  Chen Family Trust                 [LOW RISK]
                  Estate Administration — $12.8M estate
  · MLG-2026-003  TechVenture LLC                  [HIGH RISK]
                  Trade Secret — AI model misappropriation

  Also seeded:
  · 3 depositions   · 4 motions    · 3 contracts
  · 2 NLP analyses  · 6 discovery files (1 privilege-flagged)
{'='*62}
""")
