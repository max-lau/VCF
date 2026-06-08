"""
seed_firms.py — Seed firm_abc and meridian_legal with realistic demo data
Run: python3 seed_firms.py
"""
import psycopg2, os, json
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv('/root/nlp-portfolio/.env')
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
conn.autocommit = False
cur = conn.cursor()

def q(sql, params=()):
    cur.execute(sql, params)

def insert_case(firm_id, case_number, client_name, matter_number, status,
                court, judge, filing_date, description, risk_level):
    q("""INSERT INTO cases
         (firm_id, case_number, client_name, matter_number, status,
          court, judge, filing_date, description, risk_level, deleted)
         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
         RETURNING id""",
      (firm_id, case_number, client_name, matter_number, status,
       court, judge, filing_date, description, risk_level))
    return cur.fetchone()[0]

def insert_note(firm_id, case_id, author, note):
    q("""INSERT INTO case_notes (firm_id, case_id, author, note, pinned)
         VALUES (%s,%s,%s,%s,false)""",
      (firm_id, case_id, author, note))

def insert_doc(firm_id, case_id, name, source, summary, risk_score, events_json=None):
    q("""INSERT INTO case_documents
         (firm_id, case_id, document_name, source, summary, risk_score,
          events_json, doc_text, upload_date)
         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
      (firm_id, case_id, name, source, summary, risk_score,
       json.dumps(events_json) if events_json else None,
       summary))

def insert_calendar(firm_id, case_id, title, event_type, due_date,
                    description="", is_court_date=False):
    q("""INSERT INTO calendar_events
         (firm_id, matter_id, title, event_type, due_date,
          description, is_court_date, status)
         VALUES (%s,%s,%s,%s,%s,%s,%s,'scheduled')""",
      (firm_id, case_id, title, event_type, due_date,
       description, is_court_date))

def insert_contact(firm_id, case_id, name, role, org, email, phone):
    q("""INSERT INTO contacts
         (firm_id, matter_id, name, role, organization, email, phone)
         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
      (firm_id, case_id, name, role, org, email, phone))

def insert_kanban_card(firm_id, case_id, title, card_type, column_id,
                       due_date=None, moved_by_hermes=False):
    q("""INSERT INTO kanban_cards
         (firm_id, case_id, title, card_type, column_id,
          due_date, position, moved_by_hermes)
         VALUES (%s,%s,%s,%s,%s,%s,0,%s)""",
      (firm_id, case_id, title, card_type, column_id,
       due_date, moved_by_hermes))

def insert_notification(firm_id, ntype, title, body, link):
    q("""INSERT INTO notifications (firm_id, type, title, body, link)
         VALUES (%s,%s,%s,%s,%s)""",
      (firm_id, ntype, title, body, link))

today = date.today()
def d(days): return today + timedelta(days=days)
def p(days): return today - timedelta(days=days)

# ── Clear existing firm_abc and meridian_legal data ───────────────────────────
print("Clearing existing data...")
for firm in ['firm_abc', 'meridian_legal']:
    for table in ['kanban_card_logs', 'kanban_cards', 'calendar_events',
                  'contacts', 'case_notes', 'case_documents',
                  'notifications', 'cases']:
        try:
            q(f"DELETE FROM {table} WHERE firm_id=%s", (firm,))
        except Exception as e:
            print(f"  Skip {table}: {e}")
            conn.rollback()
            conn.autocommit = False

conn.commit()
print("Cleared.")

# ══════════════════════════════════════════════════════════════════════════════
# FIRM ABC — Thornton & Associates (Personal Injury / Employment)
# ══════════════════════════════════════════════════════════════════════════════
print("\nSeeding firm_abc — Thornton & Associates...")
F = 'firm_abc'

# ── Case 1: Car Accident ─────────────────────────────────────────────────────
c1 = insert_case(F, 'ABC-2024-CV-0891', 'Rivera v. Hastings Transport LLC',
    'M-2024-091', 'open', 'Superior Court of California, LA County',
    'Hon. Margaret Chen', p(180),
    'Multi-vehicle accident on I-405. Client suffered spinal injuries. Defendant is a commercial trucking company.',
    'high')

insert_doc(F, c1, 'Police Report — Incident 2024-04-12.pdf', 'uploaded',
    'LAPD traffic collision report documenting 3-vehicle accident. Defendant driver cited for unsafe lane change.',
    8.5, [{"date": "April 12, 2024", "event": "Multi-vehicle collision on I-405 northbound", "significance": "high"},
          {"date": "April 12, 2024", "event": "Defendant cited for unsafe lane change", "significance": "high"}])
insert_doc(F, c1, 'Medical Records — Cedars-Sinai 2024-04.pdf', 'uploaded',
    'Emergency admission records. L3-L4 herniated disc, T2 spinal contusion. Surgery recommended.',
    7.2)
insert_doc(F, c1, 'Expert Report — Dr. Alan Kowalski MD.pdf', 'uploaded',
    'Orthopedic expert opinion. Permanent 35% impairment rating. Future medical costs estimated $450,000.',
    6.8)
insert_doc(F, c1, 'Demand Letter — Hastings Transport.pdf', 'uploaded',
    'Settlement demand for $2.1M covering medical expenses, lost wages, pain and suffering.',
    5.0)

insert_note(F, c1, 'Sarah Thornton', 'Expert deposition scheduled for next month. Kowalski confirms permanent impairment. Strong case for punitive damages given prior violations by Hastings.')
insert_note(F, c1, 'James Rivera', 'Client reports ongoing back pain, unable to return to work as delivery driver. Lost $8,400/month income since accident.')
insert_note(F, c1, 'Sarah Thornton', 'Opposing counsel offered $450K. Rejected. Counter at $1.8M. Mediation scheduled.')

insert_calendar(F, c1, 'Mediation — JAMS Los Angeles', 'hearing', d(12),
    'JAMS mediation with Judge (Ret.) Williams. Both parties confirmed.', False)
insert_calendar(F, c1, 'Expert Deposition — Dr. Kowalski', 'deposition', d(5),
    'Zoom deposition, 9AM PST. Court reporter arranged.', False)
insert_calendar(F, c1, 'Trial Date', 'trial', d(145),
    'Jury trial. Estimated 8 days.', True)
insert_calendar(F, c1, 'Discovery Cutoff', 'deadline', d(28),
    'All discovery must be completed by this date.', False)

insert_contact(F, c1, 'Dr. Alan Kowalski MD', 'Expert Witness', 'Cedars-Sinai Medical Center',
    'akowalski@cedars.edu', '310-555-0142')
insert_contact(F, c1, 'Mark Hendricks', 'Opposing Counsel', 'Hendricks & Cole LLP',
    'mhendricks@hendrickscole.com', '213-555-0891')
insert_contact(F, c1, 'James Rivera', 'Client', 'N/A',
    'jrivera@email.com', '323-555-0234')

insert_kanban_card(F, c1, 'File motion in limine — exclude prior claims', 'motion', 'motions', d(20))
insert_kanban_card(F, c1, 'Prepare Dr. Kowalski for deposition', 'task', 'trial_prep', d(4))
insert_kanban_card(F, c1, 'Mediation brief due', 'deadline', 'motions', d(8))
insert_kanban_card(F, c1, 'Subpoena Hastings driving records', 'task', 'discovery', p(5), True)
insert_kanban_card(F, c1, 'Settlement demand letter sent', 'filing', 'discovery', p(30))

insert_notification(F, 'deadline', 'Mediation in 12 days — Rivera v. Hastings',
    'JAMS mediation scheduled. Brief due in 8 days.', '/matters/firm_abc')
insert_notification(F, 'deadline', 'Expert deposition in 5 days — Dr. Kowalski',
    'Zoom deposition 9AM PST. Court reporter confirmed.', '/calendar')

# ── Case 2: Wrongful Termination ─────────────────────────────────────────────
c2 = insert_case(F, 'ABC-2025-CV-0234', 'Patel v. TechDynamics Inc.',
    'M-2025-034', 'open', 'USDC Central District of California',
    'Hon. Robert Kim', p(90),
    'Senior engineer terminated after reporting safety violations. Retaliation claim under California Labor Code.',
    'medium')

insert_doc(F, c2, 'EEOC Charge — Patel vs TechDynamics.pdf', 'uploaded',
    'EEOC right-to-sue letter issued. Whistleblower retaliation and age discrimination claims.',
    6.5, [{"date": "January 15, 2025", "event": "EEOC charge filed", "significance": "high"},
          {"date": "March 1, 2025", "event": "Right-to-sue letter issued", "significance": "high"}])
insert_doc(F, c2, 'Employment Contract — Patel 2019.pdf', 'uploaded',
    'At-will employment with severance clause. 6 months severance if terminated without cause.',
    5.5)
insert_doc(F, c2, 'Performance Reviews 2019-2024.pdf', 'uploaded',
    'Five consecutive "Exceeds Expectations" reviews. No disciplinary actions on record.',
    7.0)

insert_note(F, c2, 'Sarah Thornton', 'Patel has strong documentation — all performance reviews excellent. Termination 3 weeks after safety report is suspicious timing.')
insert_note(F, c2, 'Priya Patel', 'Client has 12 colleagues willing to testify. Internal Slack messages suggest management discussed "managing out" Patel.')

insert_calendar(F, c2, 'Initial Case Management Conference', 'hearing', d(18),
    'Judge Kim CMC. Remote appearance.', True)
insert_calendar(F, c2, 'Interrogatories Response Due', 'deadline', d(7),
    'Defendant responses to Set 1 interrogatories due.', False)

insert_contact(F, c2, 'Priya Patel', 'Client', 'N/A', 'ppatel@email.com', '408-555-0567')
insert_contact(F, c2, 'Lisa Chang', 'Opposing Counsel', 'Wilson Sonsini', 'lchang@wsgr.com', '650-555-0891')

insert_kanban_card(F, c2, 'Draft interrogatories — set 2', 'task', 'discovery', d(14))
insert_kanban_card(F, c2, 'Preserve Slack messages — litigation hold', 'task', 'research', p(85))
insert_kanban_card(F, c2, 'CMC statement filing', 'filing', 'motions', d(15))

# ── Case 3: Slip & Fall ──────────────────────────────────────────────────────
c3 = insert_case(F, 'ABC-2025-CV-0412', 'Okonkwo v. Westfield Mall Corp.',
    'M-2025-054', 'open', 'Los Angeles Superior Court',
    'Hon. David Park', p(45),
    'Client slipped on unmarked wet floor in mall food court. Fractured hip, requires surgery.',
    'medium')

insert_doc(F, c3, 'Incident Report — Westfield 2025-04-23.pdf', 'uploaded',
    'Mall incident report. Wet floor sign not deployed. CCTV footage requested.',
    6.0, [{"date": "April 23, 2025", "event": "Slip and fall incident at Westfield food court", "significance": "high"}])
insert_doc(F, c3, 'Medical Records — Hip Fracture Surgery.pdf', 'uploaded',
    'Right hip fracture requiring total hip replacement. 6-week recovery, PT required.',
    5.8)

insert_note(F, c3, 'James Thornton', 'CCTV footage obtained — clearly shows no wet floor sign. Strong liability case.')

insert_calendar(F, c3, 'Deposition — Mall Maintenance Supervisor', 'deposition', d(22), '')
insert_calendar(F, c3, 'Site Inspection', 'deadline', d(3), 'Joint site inspection with defense expert.')

insert_contact(F, c3, 'Emmanuel Okonkwo', 'Client', 'N/A', 'eokonkwo@email.com', '424-555-0789')

insert_kanban_card(F, c3, 'Obtain CCTV footage — subpoena if needed', 'task', 'discovery', p(40), True)
insert_kanban_card(F, c3, 'Site inspection preparation', 'task', 'discovery', d(2))
insert_kanban_card(F, c3, 'File complaint', 'filing', 'intake', p(45))

# ── Case 4: Employment Discrimination ────────────────────────────────────────
c4 = insert_case(F, 'ABC-2025-CV-0578', 'Washington v. Metro Transit Authority',
    'M-2025-078', 'open', 'USDC CD California',
    'Hon. Sandra Lee', p(20),
    'Bus driver denied promotion 4 times despite superior qualifications. Race discrimination under Title VII.',
    'medium')

insert_doc(F, c4, 'EEOC Determination Letter.pdf', 'uploaded',
    'EEOC finds reasonable cause for Title VII race discrimination. Pattern of discriminatory promotions identified.',
    7.5)
insert_doc(F, c4, 'Promotion Records 2021-2024.pdf', 'uploaded',
    'Four promotion cycles. Washington ranked #1 in three. Less qualified candidates selected each time.',
    8.0)

insert_note(F, c4, 'Sarah Thornton', 'EEOC finding of reasonable cause is significant. Statistical analysis of promotion data shows clear pattern.')

insert_calendar(F, c4, 'Rule 26 Initial Disclosures Due', 'deadline', d(10), '')
insert_calendar(F, c4, 'Scheduling Conference', 'hearing', d(35), '', True)

insert_contact(F, c4, 'Marcus Washington', 'Client', 'N/A', 'mwashington@email.com', '213-555-0345')

insert_kanban_card(F, c4, 'Prepare Rule 26 initial disclosures', 'task', 'research', d(9))
insert_kanban_card(F, c4, 'Statistical expert retention', 'task', 'research', d(21))
insert_kanban_card(F, c4, 'Complaint filed', 'filing', 'intake', p(20))

# ── Case 5: Wage Theft ───────────────────────────────────────────────────────
c5 = insert_case(F, 'ABC-2025-CV-0699', 'Gomez et al. v. Pacific Harvest Farms',
    'M-2025-099', 'open', 'Fresno Superior Court',
    'Hon. Patricia Ruiz', p(10),
    'Class action. 340 farmworkers denied overtime, rest breaks, and minimum wage. PAGA claims.',
    'high')

insert_doc(F, c5, 'Class Certification Motion.pdf', 'uploaded',
    'Motion for class certification. 340 putative class members. Common questions of law and fact established.',
    7.8)
insert_doc(F, c5, 'Payroll Records Analysis.pdf', 'uploaded',
    'Expert analysis of 3 years payroll data. Average underpayment $4,200 per worker. Total exposure $1.4M.',
    8.5)

insert_note(F, c5, 'Sarah Thornton', 'Class certification hearing next month. Payroll expert analysis devastating for defendant. Settlement discussions may begin soon.')

insert_calendar(F, c5, 'Class Certification Hearing', 'hearing', d(31), '', True)
insert_calendar(F, c5, 'PAGA Notice Response Deadline', 'deadline', d(4), 'LWDA response period ends.')

insert_contact(F, c5, 'Carlos Gomez', 'Lead Plaintiff', 'N/A', 'cgomez@email.com', '559-555-0123')
insert_contact(F, c5, 'Dr. Rachel Kim', 'Economic Expert', 'UC Berkeley', 'rkim@berkeley.edu', '510-555-0456')

insert_kanban_card(F, c5, 'PAGA notice response', 'deadline', 'motions', d(4))
insert_kanban_card(F, c5, 'Class cert reply brief', 'motion', 'motions', d(21))
insert_kanban_card(F, c5, 'Payroll records analysis complete', 'task', 'discovery', p(5), True)
insert_kanban_card(F, c5, 'Complaint and PAGA notice filed', 'filing', 'intake', p(10))

conn.commit()
print(f"firm_abc seeded: 5 cases")

# ══════════════════════════════════════════════════════════════════════════════
# MERIDIAN LEGAL — Corporate / Commercial Litigation
# ══════════════════════════════════════════════════════════════════════════════
print("\nSeeding meridian_legal — Meridian Legal Group...")
F = 'meridian_legal'

# ── Case 1: Contract Dispute ─────────────────────────────────────────────────
m1 = insert_case(F, 'ML-2024-CV-1142', 'NovaTech Solutions v. Apex Systems Inc.',
    'M-2024-142', 'open', 'USDC SDNY',
    'Hon. James Patterson', p(210),
    'Software development contract dispute. $8.7M at stake. Defendant failed to deliver ERP system per specifications.',
    'high')

insert_doc(F, m1, 'Software Development Agreement 2022.pdf', 'uploaded',
    'Master services agreement. Fixed price $8.7M. Deliverables, milestones, and acceptance criteria defined.',
    7.0, [{"date": "March 15, 2022", "event": "Software development agreement executed", "significance": "high"},
          {"date": "December 31, 2023", "event": "Final delivery deadline missed by defendant", "significance": "high"}])
insert_doc(F, m1, 'Technical Expert Report — Dr. Singh.pdf', 'uploaded',
    'Expert analysis confirms system fails 67% of acceptance tests. Fundamental architectural defects.',
    8.2)
insert_doc(F, m1, 'Damages Report — Forensic Accounting.pdf', 'uploaded',
    'Direct damages $8.7M. Consequential damages $3.2M including lost business opportunities.',
    7.5)
insert_doc(F, m1, 'Motion for Summary Judgment.pdf', 'uploaded',
    'MSJ filed on liability. Contract terms unambiguous. Defendant in clear breach.',
    6.5)

insert_note(F, m1, 'Victoria Meridian', 'MSJ fully briefed. Judge Patterson has strong record of granting MSJ in clear contract cases. Oral argument in 3 weeks.')
insert_note(F, m1, 'Victoria Meridian', 'Apex offered $2.1M. Rejected. Our damages are clear and well-documented. Holding firm at $11.9M.')
insert_note(F, m1, 'David Chen', 'Technical expert preparation complete. Dr. Singh very credible — 30 years ERP implementation experience.')

insert_calendar(F, m1, 'MSJ Oral Argument', 'hearing', d(21), 'SDNY Courtroom 14B, 2PM.', True)
insert_calendar(F, m1, 'Trial Date (if MSJ denied)', 'trial', d(120), '10-day jury trial estimated.', True)
insert_calendar(F, m1, 'Pre-trial Conference', 'hearing', d(90), '', True)

insert_contact(F, m1, 'Dr. Rajan Singh', 'Technical Expert', 'MIT Computer Science', 'rsingh@mit.edu', '617-555-0891')
insert_contact(F, m1, 'Sarah Blake', 'Opposing Counsel', 'Skadden Arps', 'sblake@skadden.com', '212-555-0456')
insert_contact(F, m1, 'Robert Novak', 'Client CEO', 'NovaTech Solutions', 'rnovak@novatech.com', '212-555-0789')

insert_kanban_card(F, m1, 'MSJ oral argument preparation', 'task', 'trial_prep', d(18))
insert_kanban_card(F, m1, 'Pre-trial exhibit list', 'deadline', 'trial_prep', d(75))
insert_kanban_card(F, m1, 'Motion for summary judgment filed', 'motion', 'motions', p(30), True)
insert_kanban_card(F, m1, 'Technical expert report finalized', 'task', 'discovery', p(45))
insert_kanban_card(F, m1, 'Complaint filed', 'filing', 'intake', p(210))

insert_notification(F, 'deadline', 'MSJ Oral Argument in 21 days — NovaTech v. Apex',
    'SDNY Courtroom 14B, 2PM. Preparation materials due this week.', '/calendar')

# ── Case 2: IP Infringement ───────────────────────────────────────────────────
m2 = insert_case(F, 'ML-2025-CV-0089', 'BioSynth Corp. v. GeneriPharm Ltd.',
    'M-2025-089', 'open', 'USDC Delaware',
    'Hon. Kathleen Murphy', p(120),
    'Patent infringement. BioSynth patents on drug synthesis process. Defendant selling generic infringing product.',
    'high')

insert_doc(F, m2, 'Patent Portfolio — US10,234,567 and US10,891,234.pdf', 'uploaded',
    'Two utility patents on novel drug synthesis process. Both valid and enforceable. USPTO confirmed.',
    8.0, [{"date": "June 2019", "event": "US10,234,567 patent granted", "significance": "high"},
          {"date": "January 2021", "event": "US10,891,234 continuation patent granted", "significance": "high"}])
insert_doc(F, m2, 'Claim Chart — Infringement Analysis.pdf', 'uploaded',
    'Element-by-element claim chart. All 12 claims of US10,234,567 literally infringed by GeneriPharm product.',
    8.5)
insert_doc(F, m2, 'Preliminary Injunction Motion.pdf', 'uploaded',
    'PI motion filed. Irreparable harm clear. Market share loss $2M/month.',
    7.2)

insert_note(F, m2, 'Victoria Meridian', 'PI hearing next week. Delaware courts favorable to patent holders. Strong likelihood of success on merits.')
insert_note(F, m2, 'James Whitfield', 'GeneriPharm filed IPR petition challenging validity. Need to coordinate litigation hold with PTAB proceedings.')

insert_calendar(F, m2, 'Preliminary Injunction Hearing', 'hearing', d(8), 'Delaware federal court, 10AM.', True)
insert_calendar(F, m2, 'Markman Hearing (Claim Construction)', 'hearing', d(65), '', True)
insert_calendar(F, m2, 'IPR Response Due — PTAB', 'deadline', d(35), 'Patent Trial and Appeal Board response.')

insert_contact(F, m2, 'Dr. Elena Vasquez', 'Patent Expert', 'Stanford IP Clinic', 'evasquez@stanford.edu', '650-555-0234')
insert_contact(F, m2, 'Thomas Greene', 'Opposing Counsel', 'Fish & Richardson', 'tgreene@fr.com', '302-555-0567')

insert_kanban_card(F, m2, 'PI hearing preparation', 'task', 'trial_prep', d(6))
insert_kanban_card(F, m2, 'IPR response — PTAB', 'deadline', 'motions', d(35))
insert_kanban_card(F, m2, 'Claim construction brief', 'motion', 'motions', d(50))
insert_kanban_card(F, m2, 'Preliminary injunction filed', 'motion', 'motions', p(14), True)

insert_notification(F, 'deadline', 'PI Hearing in 8 days — BioSynth v. GeneriPharm',
    'Delaware federal court, 10AM. Critical hearing for preliminary injunction.', '/calendar')
insert_notification(F, 'hermes', '🤖 Hermes: IPR deadline approaching',
    'PTAB response due in 35 days. Coordination required with litigation team.', '/calendar')

# ── Case 3: Shareholder Derivative ───────────────────────────────────────────
m3 = insert_case(F, 'ML-2025-CV-0234', 'In re: Pinnacle Energy Corp. Derivative Litigation',
    'M-2025-234', 'open', 'Delaware Court of Chancery',
    'Vice Chancellor William Harris', p(60),
    'Shareholder derivative suit. Board approved $45M acquisition without proper due diligence. Breach of fiduciary duty.',
    'high')

insert_doc(F, m3, 'Verified Shareholder Derivative Complaint.pdf', 'uploaded',
    'Derivative complaint. Demand futility alleged. Board conflicted — 5 of 7 directors received acquisition fees.',
    8.0)
insert_doc(F, m3, 'Board Minutes — Acquisition Approval.pdf', 'uploaded',
    'Board meeting minutes. 47-minute meeting to approve $45M acquisition. No independent financial advisor retained.',
    9.0, [{"date": "November 2024", "event": "Board approves $45M acquisition in 47-minute meeting", "significance": "high"}])

insert_note(F, m3, 'Victoria Meridian', 'Board minutes are damning — 47 minutes for $45M decision with no financial advisor. Business judgment rule will be hard to invoke.')
insert_note(F, m3, 'Associate', 'Delaware Chancery very plaintiff-friendly in fiduciary duty cases. Strong case.')

insert_calendar(F, m3, 'Motion to Dismiss Hearing', 'hearing', d(42), 'Court of Chancery, Dover DE.', True)
insert_calendar(F, m3, 'Discovery Opens (if MTD denied)', 'deadline', d(90), '')

insert_contact(F, m3, 'Margaret Sullivan', 'Lead Plaintiff', 'Institutional Shareholder', 'msullivan@pensionfund.com', '302-555-0890')

insert_kanban_card(F, m3, 'Opposition to motion to dismiss', 'motion', 'motions', d(28))
insert_kanban_card(F, m3, 'Board deposition preparation', 'task', 'research', d(55))
insert_kanban_card(F, m3, 'Complaint filed', 'filing', 'intake', p(60))

# ── Case 4: Commercial Real Estate ───────────────────────────────────────────
m4 = insert_case(F, 'ML-2025-CV-0445', 'Harborview Properties v. Coastal Development LLC',
    'M-2025-445', 'open', 'Miami-Dade Circuit Court',
    'Hon. Carlos Mendez', p(30),
    'Commercial landlord-tenant dispute. $12M lease breach. Tenant abandoned 80,000 sq ft office space mid-lease.',
    'medium')

insert_doc(F, m4, 'Commercial Lease Agreement 2021-2031.pdf', 'uploaded',
    '10-year lease, $120,000/month. Personal guarantee from CEO. Abandonment clause triggers full acceleration.',
    7.5)
insert_doc(F, m4, 'Notice of Default and Acceleration.pdf', 'uploaded',
    'Notice sent March 2025. Tenant 90 days delinquent. $360,000 arrears plus $11.64M accelerated.',
    7.0)

insert_note(F, m4, 'James Whitfield', 'Personal guarantee is solid. CEO has $8M in personal assets. Attachment motion filed.')

insert_calendar(F, m4, 'Preliminary Injunction — Asset Freeze', 'hearing', d(5), 'Emergency hearing.', True)
insert_calendar(F, m4, 'Answer Deadline', 'deadline', d(15), 'Defendant answer due.')

insert_contact(F, m4, 'Frank Harborview', 'Client', 'Harborview Properties', 'frank@harborview.com', '305-555-0123')

insert_kanban_card(F, m4, 'Emergency asset freeze motion', 'motion', 'motions', d(3))
insert_kanban_card(F, m4, 'Complaint and lis pendens filed', 'filing', 'intake', p(30))
insert_kanban_card(F, m4, 'Personal guarantee demand letter', 'deadline', 'research', p(25))

insert_notification(F, 'deadline', 'Emergency Hearing in 5 days — Harborview v. Coastal',
    'Asset freeze motion. Miami-Dade Circuit Court.', '/calendar')

# ── Case 5: Securities Fraud ──────────────────────────────────────────────────
m5 = insert_case(F, 'ML-2024-CV-2891', 'SEC v. Meridian Client — Defense Matter',
    'M-2024-891', 'open', 'USDC SDNY',
    'Hon. Barbara Winters', p(300),
    'Defense of former CFO in SEC enforcement action. Alleged material misstatements in quarterly earnings.',
    'high')

insert_doc(F, m5, 'SEC Wells Notice Response.pdf', 'uploaded',
    'Response to Wells Notice. 47-page submission explaining accounting methodology. GAAP compliance demonstrated.',
    8.8)
insert_doc(F, m5, 'Expert Report — Forensic Accounting.pdf', 'uploaded',
    'Expert opinion: revenue recognition methodology compliant with ASC 606. No intentional misstatement.',
    8.0)
insert_doc(F, m5, 'SEC Complaint.pdf', 'uploaded',
    'SEC alleges $230M revenue overstatement over 3 years. Civil penalty and disgorgement sought.',
    9.5, [{"date": "2021-2023", "event": "Alleged revenue overstatement period", "significance": "high"},
          {"date": "September 2024", "event": "SEC files civil enforcement action", "significance": "high"}])

insert_note(F, m5, 'Victoria Meridian', 'SEC case weak on intent — key element for fraud. Accounting methodology was disclosed and reviewed by Big 4 auditor. Recommend fighting rather than settling.')
insert_note(F, m5, 'Victoria Meridian', 'Client anxious. Reassured that SEC must prove scienter. Our expert directly contradicts SEC expert on GAAP compliance.')

insert_calendar(F, m5, 'Status Conference — Judge Winters', 'hearing', d(14), 'SDNY, 10AM.', True)
insert_calendar(F, m5, 'Expert Discovery Cutoff', 'deadline', d(45), '')
insert_calendar(F, m5, 'Summary Judgment Deadline', 'deadline', d(90), '')

insert_contact(F, m5, 'Jonathan Reid', 'Client — Former CFO', 'N/A', 'jreid@private.com', '212-555-0999')
insert_contact(F, m5, 'SEC Trial Counsel', 'Opposing — Government', 'SEC Division of Enforcement', 'sec.enforcement@sec.gov', '202-555-0100')
insert_contact(F, m5, 'Prof. Mark Davidson CPA', 'Accounting Expert', 'NYU Stern', 'mdavidson@stern.nyu.edu', '212-555-0345')

insert_kanban_card(F, m5, 'Status conference preparation', 'task', 'trial_prep', d(12))
insert_kanban_card(F, m5, 'Expert rebuttal report — accounting', 'task', 'discovery', d(40))
insert_kanban_card(F, m5, 'Motion to dismiss — scienter element', 'motion', 'motions', d(60))
insert_kanban_card(F, m5, 'Wells Notice response filed', 'filing', 'research', p(180), True)
insert_kanban_card(F, m5, 'SEC complaint answered', 'filing', 'intake', p(270))

conn.commit()
print(f"meridian_legal seeded: 5 cases")

# ── Final count ───────────────────────────────────────────────────────────────
print("\n=== Seeding Complete ===")
for firm in ['firm_abc', 'meridian_legal']:
    cur.execute("SELECT COUNT(*) FROM cases WHERE firm_id=%s", (firm,))
    cases = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kanban_cards WHERE firm_id=%s", (firm,))
    cards = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM calendar_events WHERE firm_id=%s", (firm,))
    events = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM contacts WHERE firm_id=%s", (firm,))
    contacts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM case_documents WHERE firm_id=%s", (firm,))
    docs = cur.fetchone()[0]
    print(f"{firm}: {cases} cases, {docs} docs, {cards} kanban cards, {events} calendar events, {contacts} contacts")

conn.close()
