"""
generate_dataset.py
===================

Creates a synthetic but realistic enterprise dataset for the RAG challenge.

Company: "Nimbus Industries" — a mid-size technology manufacturer.

It produces every data type the challenge requires:
  * PDFs & internal documents  -> data/documents/*.pdf
  * SQL / CSV databases        -> data/structured/*.csv + schema.sql
  * JSON logs & audit trails   -> data/logs/*.json
  * Compliance / technical docs-> data/documents/*.pdf
  * Operational datasets       -> data/structured/*.csv
  * Metadata & access policies -> data/access/access_policies.json
  * User-role mappings         -> data/access/users.json

Every artefact carries metadata: {department, sensitivity, source_type}.
This metadata is what the RBAC engine later uses to decide who can see what.

Run:
    python generate_dataset.py

Dependencies:  faker, fpdf2   (pip install faker fpdf2)
"""
import csv
import json
import random
from datetime import datetime, timedelta

from faker import Faker
from fpdf import FPDF

from config import (
    DOCS_DIR,
    STRUCT_DIR,
    LOGS_DIR,
    ACCESS_DIR,
    DEPARTMENTS,
)

fake = Faker()
Faker.seed(42)
random.seed(42)

# A running manifest: every document/record we create is registered here so
# the ingestion step has a single index of "what exists + its access metadata".
MANIFEST = []


def register(source_type, path, department, sensitivity, title, extra=None):
    """Record an artefact and its access metadata into the global manifest."""
    entry = {
        "doc_id": f"DOC-{len(MANIFEST) + 1:04d}",
        "source_type": source_type,
        "path": str(path),
        "department": department,
        "sensitivity": sensitivity,
        "title": title,
    }
    if extra:
        entry.update(extra)
    MANIFEST.append(entry)
    return entry["doc_id"]


# ---------------------------------------------------------------------------
# Helpers to write a clean PDF
# ---------------------------------------------------------------------------
def write_pdf(path, title, body_paragraphs):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, title)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 11)
    for para in body_paragraphs:
        # Encode to latin-1 safe text (fpdf core fonts are latin-1).
        safe = para.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 6, safe)
        pdf.ln(2)
    pdf.output(str(path))


# ===========================================================================
# 1. PDF DOCUMENTS  (reports, policies, compliance, technical)
# ===========================================================================
def gen_documents():
    docs = [
        # (filename, dept, sensitivity, title, paragraphs)
        (
            "finance_q3_report.pdf", "Finance", "confidential",
            "Nimbus Industries - Q3 2025 Financial Report",
            [
                "Executive Summary: Q3 2025 revenue reached $48.2M, up 12% "
                "quarter-over-quarter, driven primarily by the Industrial "
                "Sensors product line. Gross margin held steady at 41%.",
                "Operating Expenses: Total operating expenses were $29.4M. "
                "R&D spending increased to $7.1M as the company accelerated "
                "the Helios platform roadmap.",
                "Cash Position: The company closed the quarter with $63.5M in "
                "cash and equivalents. The board approved a $5M share buyback.",
                "Outlook: Management guides Q4 revenue between $50M and $53M, "
                "contingent on the resolution of supply-chain constraints in "
                "the Shenzhen facility.",
            ],
        ),
        (
            "hr_policy_handbook.pdf", "HR", "internal",
            "Nimbus Industries - Employee Policy Handbook 2025",
            [
                "Working Hours: Standard working hours are 9:00 to 17:30, "
                "Monday through Friday. Employees may request hybrid schedules "
                "with manager approval.",
                "Leave Policy: Full-time employees accrue 22 days of paid "
                "annual leave plus 10 public holidays. Unused leave may carry "
                "over up to 5 days into the next calendar year.",
                "Code of Conduct: All employees must complete annual "
                "anti-harassment and data-privacy training. Violations are "
                "handled through the HR grievance procedure.",
                "Remote Work Security: Employees working remotely must use the "
                "company VPN and approved devices when accessing internal "
                "systems.",
            ],
        ),
        (
            "hr_compensation_bands.pdf", "HR", "restricted",
            "Nimbus Industries - Compensation Bands (RESTRICTED)",
            [
                "Band L3 (Engineer II): base salary range $82,000 - $98,000, "
                "annual bonus target 8%.",
                "Band L5 (Senior Engineer): base salary range $128,000 - "
                "$155,000, annual bonus target 12%, equity eligible.",
                "Band M2 (Director): base salary range $185,000 - $225,000, "
                "annual bonus target 20%, equity grant 4,000 RSUs.",
                "Executive compensation is determined by the Compensation "
                "Committee and is not disclosed in this document.",
            ],
        ),
        (
            "eng_helios_architecture.pdf", "Engineering", "confidential",
            "Helios Platform - System Architecture Specification",
            [
                "Overview: Helios is a distributed telemetry platform ingesting "
                "up to 2 million sensor events per second. It is composed of an "
                "ingestion tier, a stream-processing tier, and a query tier.",
                "Ingestion Tier: Built on a partitioned message bus. Each sensor "
                "gateway authenticates with mutual TLS and publishes to a "
                "regional broker cluster.",
                "Storage: Hot data is retained for 7 days in an in-memory "
                "column store; cold data is tiered to object storage in Parquet "
                "format with 90-day retention.",
                "Known Risk: The query tier currently lacks rate limiting, which "
                "was flagged in incident INC-2041 as a potential availability "
                "risk under burst load.",
            ],
        ),
        (
            "eng_security_review.pdf", "Engineering", "restricted",
            "Helios Platform - Security Review (RESTRICTED)",
            [
                "Finding SEC-01 (High): The internal admin dashboard was "
                "accessible without MFA from the corporate network. Remediation "
                "is tracked under ticket ENG-3320.",
                "Finding SEC-02 (Medium): API keys for the partner integration "
                "were stored in plaintext in a configuration file. Keys have "
                "since been rotated and moved to the secrets manager.",
                "Finding SEC-03 (Low): Verbose error messages leaked stack "
                "traces to unauthenticated users on the status endpoint.",
                "Overall Posture: Acceptable with remediation. A follow-up "
                "review is scheduled for the next quarter.",
            ],
        ),
        (
            "legal_compliance_gdpr.pdf", "Legal", "confidential",
            "Data Protection & GDPR Compliance Record 2025",
            [
                "Lawful Basis: Customer telemetry is processed under legitimate "
                "interest; marketing communications require explicit consent.",
                "Data Subject Requests: In 2025 the company processed 37 access "
                "requests and 12 erasure requests, all completed within the "
                "30-day statutory window.",
                "Data Breach Register: One reportable incident (INC-2041 related "
                "exposure) was assessed as low risk and notified to the "
                "supervisory authority within 72 hours.",
                "Sub-processors: A current list of sub-processors and their data "
                "processing agreements is maintained by the Legal department.",
            ],
        ),
        (
            "ops_runbook.pdf", "Operations", "internal",
            "Operations Runbook - Production Incident Response",
            [
                "Severity Definitions: SEV-1 is a full customer-facing outage; "
                "SEV-2 is partial degradation; SEV-3 is a minor issue with a "
                "workaround.",
                "On-call Rotation: The primary on-call engineer acknowledges "
                "pages within 5 minutes. Escalation to the secondary occurs "
                "after 15 minutes of no response.",
                "Communication: For SEV-1 incidents, a status page update must "
                "be posted within 20 minutes and every 30 minutes thereafter.",
                "Post-mortem: A blameless post-mortem is required within 5 "
                "business days of any SEV-1 or SEV-2 incident.",
            ],
        ),
        (
            "sales_playbook.pdf", "Sales", "internal",
            "Enterprise Sales Playbook 2025",
            [
                "Target Segments: The primary focus is industrial manufacturing "
                "accounts with more than 500 connected devices.",
                "Discount Authority: Account executives may approve discounts up "
                "to 10%. Discounts between 10% and 20% require director sign-off.",
                "Standard Terms: Default contract term is 24 months with annual "
                "billing. Net-30 payment terms are standard.",
                "Competitive Positioning: Against legacy SCADA vendors, lead "
                "with total cost of ownership and the Helios analytics suite.",
            ],
        ),
    ]

    for fname, dept, sens, title, paras in docs:
        path = DOCS_DIR / fname
        write_pdf(path, title, paras)
        register("pdf", path, dept, sens, title)
    print(f"  documents : {len(docs)} PDFs")


# ===========================================================================
# 2. STRUCTURED DATA  (CSV + a SQL schema dump)
# ===========================================================================
def gen_structured():
    count = 0

    # ---- Finance: transactions (confidential) ----
    path = STRUCT_DIR / "finance_transactions.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["txn_id", "date", "vendor", "category", "amount_usd", "status"])
        cats = ["Cloud Infra", "Hardware", "Travel", "Marketing", "Payroll", "Legal"]
        for i in range(60):
            d = datetime(2025, 1, 1) + timedelta(days=random.randint(0, 260))
            w.writerow([
                f"TXN-{1000 + i}",
                d.strftime("%Y-%m-%d"),
                fake.company(),
                random.choice(cats),
                round(random.uniform(500, 95000), 2),
                random.choice(["paid", "paid", "paid", "pending"]),
            ])
    register("csv", path, "Finance", "confidential",
             "Finance Transactions Ledger 2025")
    count += 1

    # ---- HR: employee directory (restricted, contains salary) ----
    path = STRUCT_DIR / "hr_employees.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["emp_id", "name", "department", "title", "salary_usd", "manager"])
        for i in range(40):
            dept = random.choice(DEPARTMENTS)
            w.writerow([
                f"EMP-{200 + i}",
                fake.name(),
                dept,
                random.choice(["Engineer II", "Senior Engineer", "Analyst",
                               "Manager", "Specialist", "Director"]),
                random.randint(70000, 230000),
                fake.name(),
            ])
    register("csv", path, "HR", "restricted",
             "HR Employee Directory with Compensation")
    count += 1

    # ---- Sales: customer accounts (confidential) ----
    path = STRUCT_DIR / "sales_accounts.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "customer", "region", "arr_usd",
                    "devices", "renewal_date"])
        for i in range(50):
            d = datetime(2025, 6, 1) + timedelta(days=random.randint(0, 400))
            w.writerow([
                f"ACC-{500 + i}",
                fake.company(),
                random.choice(["NA", "EMEA", "APAC", "LATAM"]),
                random.randint(20000, 900000),
                random.randint(120, 8000),
                d.strftime("%Y-%m-%d"),
            ])
    register("csv", path, "Sales", "confidential",
             "Sales Customer Accounts & ARR")
    count += 1

    # ---- Operations: device fleet telemetry summary (internal) ----
    path = STRUCT_DIR / "ops_device_fleet.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["device_id", "site", "model", "uptime_pct",
                    "firmware", "last_seen"])
        for i in range(70):
            d = datetime(2025, 9, 1) + timedelta(hours=random.randint(0, 200))
            w.writerow([
                f"DEV-{9000 + i}",
                random.choice(["Shenzhen", "Austin", "Berlin", "Pune"]),
                random.choice(["NS-100", "NS-200", "NS-Pro"]),
                round(random.uniform(95.0, 99.99), 2),
                f"v{random.randint(2,4)}.{random.randint(0,9)}.{random.randint(0,9)}",
                d.strftime("%Y-%m-%d %H:%M"),
            ])
    register("csv", path, "Operations", "internal",
             "Operations Device Fleet Telemetry Summary")
    count += 1

    # ---- A SQL schema dump (so the 'SQL database' box is literally ticked) ----
    sql_path = STRUCT_DIR / "schema.sql"
    sql_path.write_text(
        "-- Nimbus Industries core schema (illustrative dump)\n"
        "CREATE TABLE finance_transactions (\n"
        "    txn_id      VARCHAR PRIMARY KEY,\n"
        "    date        DATE,\n"
        "    vendor      VARCHAR,\n"
        "    category    VARCHAR,\n"
        "    amount_usd  NUMERIC,\n"
        "    status      VARCHAR\n"
        ");\n\n"
        "CREATE TABLE hr_employees (\n"
        "    emp_id      VARCHAR PRIMARY KEY,\n"
        "    name        VARCHAR,\n"
        "    department  VARCHAR,\n"
        "    title       VARCHAR,\n"
        "    salary_usd  NUMERIC,   -- RESTRICTED column\n"
        "    manager     VARCHAR\n"
        ");\n"
    )
    register("sql", sql_path, "Finance", "internal",
             "Database Schema Definition")
    count += 1

    print(f"  structured: {count} CSV/SQL files")


# ===========================================================================
# 3. JSON LOGS & AUDIT TRAILS
# ===========================================================================
def gen_logs():
    count = 0

    # ---- Engineering incident log (confidential) ----
    incidents = []
    for i in range(8):
        sev = random.choice(["SEV-1", "SEV-2", "SEV-3"])
        ts = datetime(2025, 8, 1) + timedelta(days=i * 7, hours=random.randint(0, 23))
        incidents.append({
            "incident_id": f"INC-{2040 + i}",
            "severity": sev,
            "service": random.choice(["helios-ingest", "helios-query",
                                      "auth-service", "billing"]),
            "summary": fake.sentence(nb_words=10),
            "started_at": ts.isoformat(),
            "resolved_minutes": random.randint(12, 480),
            "root_cause": random.choice([
                "query tier overload under burst traffic",
                "expired TLS certificate",
                "database connection pool exhaustion",
                "bad deploy rolled back",
            ]),
        })
    path = LOGS_DIR / "eng_incidents.json"
    path.write_text(json.dumps(incidents, indent=2))
    register("json", path, "Engineering", "confidential",
             "Engineering Incident Log")
    count += 1

    # ---- Security / access audit trail (restricted) ----
    audit = []
    actions = ["login", "download", "permission_change", "export", "delete"]
    for i in range(40):
        ts = datetime(2025, 9, 1) + timedelta(minutes=random.randint(0, 40000))
        audit.append({
            "event_id": f"AUD-{5000 + i}",
            "timestamp": ts.isoformat(),
            "user": fake.user_name(),
            "action": random.choice(actions),
            "resource": random.choice([
                "hr_employees.csv", "finance_q3_report.pdf",
                "eng_security_review.pdf", "sales_accounts.csv",
            ]),
            "result": random.choice(["allowed", "allowed", "allowed", "denied"]),
            "ip": fake.ipv4(),
        })
    path = LOGS_DIR / "security_audit_trail.json"
    path.write_text(json.dumps(audit, indent=2))
    register("json", path, "Legal", "restricted",
             "Security Access Audit Trail")
    count += 1

    # ---- Operations alerts (internal) ----
    alerts = []
    for i in range(15):
        ts = datetime(2025, 9, 10) + timedelta(hours=i * 3)
        alerts.append({
            "alert_id": f"ALRT-{700 + i}",
            "timestamp": ts.isoformat(),
            "severity": random.choice(["warning", "critical", "info"]),
            "metric": random.choice(["cpu", "memory", "disk", "latency_p99"]),
            "value": round(random.uniform(60, 99), 1),
            "site": random.choice(["Shenzhen", "Austin", "Berlin", "Pune"]),
            "acknowledged": random.choice([True, False]),
        })
    path = LOGS_DIR / "ops_alerts.json"
    path.write_text(json.dumps(alerts, indent=2))
    register("json", path, "Operations", "internal",
             "Operations Monitoring Alerts")
    count += 1

    print(f"  logs      : {count} JSON files")


# ===========================================================================
# 4. ACCESS CONTROL:  policies + user-role mappings
# ===========================================================================
def gen_access_control():
    # Role -> what departments it can read + the max sensitivity it can see.
    # 'departments == "*"' means all departments.
    access_policies = {
        "employee": {
            "description": "General staff. Public/internal info only.",
            "departments": "*",
            "max_sensitivity": "internal",
        },
        "finance_analyst": {
            "description": "Finance team member.",
            "departments": ["Finance"],
            "max_sensitivity": "confidential",
        },
        "hr_manager": {
            "description": "HR manager. Can see restricted HR data (salaries).",
            "departments": ["HR"],
            "max_sensitivity": "restricted",
        },
        "engineer": {
            "description": "Engineering staff.",
            "departments": ["Engineering", "Operations"],
            "max_sensitivity": "confidential",
        },
        "legal_counsel": {
            "description": "Legal & compliance. Sees restricted audit/compliance.",
            "departments": ["Legal", "HR"],
            "max_sensitivity": "restricted",
        },
        "sales_rep": {
            "description": "Sales representative.",
            "departments": ["Sales"],
            "max_sensitivity": "confidential",
        },
        "executive": {
            "description": "C-level. Cross-department, up to confidential.",
            "departments": "*",
            "max_sensitivity": "confidential",
        },
        "admin": {
            "description": "System administrator. Full access to everything.",
            "departments": "*",
            "max_sensitivity": "restricted",
        },
    }
    path = ACCESS_DIR / "access_policies.json"
    path.write_text(json.dumps(access_policies, indent=2))

    # User -> role mapping (the people who will query the assistant).
    users = {
        "alice":   {"name": "Alice Chen",    "role": "finance_analyst", "department": "Finance"},
        "bob":     {"name": "Bob Martinez",  "role": "engineer",        "department": "Engineering"},
        "carol":   {"name": "Carol Singh",   "role": "hr_manager",      "department": "HR"},
        "dave":    {"name": "Dave Okafor",   "role": "sales_rep",       "department": "Sales"},
        "erin":    {"name": "Erin Walsh",    "role": "legal_counsel",   "department": "Legal"},
        "frank":   {"name": "Frank Liu",     "role": "employee",        "department": "Operations"},
        "grace":   {"name": "Grace Kim",     "role": "executive",       "department": "Executive"},
        "root":    {"name": "System Admin",  "role": "admin",           "department": "IT"},
    }
    path = ACCESS_DIR / "users.json"
    path.write_text(json.dumps(users, indent=2))

    print(f"  access    : {len(access_policies)} roles, {len(users)} users")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    print("Generating synthetic enterprise dataset for Nimbus Industries...")
    gen_documents()
    gen_structured()
    gen_logs()
    gen_access_control()

    # Write the manifest that ingestion will read.
    manifest_path = ACCESS_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST, indent=2))
    print(f"  manifest  : {len(MANIFEST)} source artefacts registered")
    print("\nDone. Data written under ./data/")


if __name__ == "__main__":
    main()
