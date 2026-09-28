
import os
import random
import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

import psycopg2
from psycopg2.extras import Json
from faker import Faker



def unique_number(prefix):
    """Generate a unique human-readable ITSM record number."""
    return f"{prefix}{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}{uuid.uuid4().hex[:4].upper()}"

fake = Faker()
random.seed()

DB = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "seip_itsm"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

GROUPS = {
    "Database": ["DBA-PostgreSQL", "DBA-Oracle", "DBA-Sybase"],
    "Network": ["Network-L2", "Network-L3", "Network-Security"],
    "Unix": ["Unix-L2", "Unix-L3"],
    "RedHat": ["Linux-RHEL-L2", "Linux-RHEL-L3"],
    "ServiceNow": ["SNOW-Platform", "SNOW-Integration", "SNOW-Admin"],
}

PATTERNS = [
    {
        "id": "DB_CONN_POOL_EXHAUSTION",
        "tech": "Database",
        "category": "Database",
        "subcategory": "PostgreSQL",
        "service": "Customer API",
        "symptom": "database connection pool exhausted",
        "desc": "Application requests are failing because the PostgreSQL connection pool is exhausted",
        "root": "Connection leak in application worker process",
        "runbook": "Restart affected application workers, inspect active sessions, identify idle-in-transaction sessions, and validate pool recovery",
        "metric": ("db_connections_used_pct", 98, 80),
        "group": "DBA-PostgreSQL",
    },
    {
        "id": "DB_LONG_RUNNING_QUERY",
        "tech": "Database",
        "category": "Database",
        "subcategory": "PostgreSQL",
        "service": "Order Processing",
        "symptom": "long running database query",
        "desc": "Transaction processing is delayed by a long-running PostgreSQL query",
        "root": "Missing index causing sequential scan on high-volume table",
        "runbook": "Capture pg_stat_activity, obtain EXPLAIN plan, identify blocking sessions, and validate index recommendation",
        "metric": ("query_duration_seconds", 940, 300),
        "group": "DBA-PostgreSQL",
    },
    {
        "id": "NET_PACKET_LOSS",
        "tech": "Network",
        "category": "Network",
        "subcategory": "Connectivity",
        "service": "Corporate Network",
        "symptom": "packet loss detected on network interface",
        "desc": "Intermittent packet loss is impacting application connectivity",
        "root": "Faulty interface/transceiver or degraded network path",
        "runbook": "Check interface errors, run path diagnostics, compare peer interface counters, and replace faulty component if confirmed",
        "metric": ("packet_loss_pct", 12, 2),
        "group": "Network-L3",
    },
    {
        "id": "NET_HIGH_LATENCY",
        "tech": "Network",
        "category": "Network",
        "subcategory": "Latency",
        "service": "Payment Gateway",
        "symptom": "network latency above threshold",
        "desc": "Payment gateway calls are experiencing elevated network latency",
        "root": "Routing path congestion",
        "runbook": "Run traceroute, inspect routing changes, compare latency by path, and engage network engineering",
        "metric": ("latency_ms", 420, 150),
        "group": "Network-L3",
    },
    {
        "id": "UNIX_FILESYSTEM",
        "tech": "Unix",
        "category": "Unix",
        "subcategory": "Filesystem",
        "service": "Batch Processing",
        "symptom": "filesystem utilization above threshold",
        "desc": "Unix filesystem utilization is critically high",
        "root": "Temporary/log files were not rotated or cleaned",
        "runbook": "Identify largest files, validate retention policy, archive/delete approved files, and verify filesystem recovery",
        "metric": ("filesystem_used_pct", 96, 85),
        "group": "Unix-L2",
    },
    {
        "id": "RHEL_CPU",
        "tech": "RedHat",
        "category": "Server",
        "subcategory": "CPU",
        "service": "Application Server",
        "symptom": "RHEL CPU utilization above threshold",
        "desc": "Application server CPU utilization has remained high",
        "root": "Runaway process or unexpected batch workload",
        "runbook": "Capture top processes, inspect service logs, correlate with scheduled jobs, and restart only after approval",
        "metric": ("cpu_used_pct", 97, 85),
        "group": "Linux-RHEL-L2",
    },
    {
        "id": "RHEL_MEMORY",
        "tech": "RedHat",
        "category": "Server",
        "subcategory": "Memory",
        "service": "Integration Server",
        "symptom": "RHEL memory utilization above threshold",
        "desc": "Integration server is reporting sustained memory pressure",
        "root": "Memory leak in integration worker",
        "runbook": "Inspect memory consumers, collect process statistics, restart affected worker under change control, and validate memory stabilization",
        "metric": ("memory_used_pct", 94, 85),
        "group": "Linux-RHEL-L2",
    },
    {
        "id": "SNOW_INTEGRATION_FAILURE",
        "tech": "ServiceNow",
        "category": "ServiceNow",
        "subcategory": "Integration",
        "service": "ServiceNow Integration",
        "symptom": "ServiceNow integration queue backlog",
        "desc": "Integration messages are accumulating in the ServiceNow queue",
        "root": "Authentication/token failure against downstream endpoint",
        "runbook": "Check integration logs, validate credentials/token, retry failed messages, and verify queue drain",
        "metric": ("queue_depth", 850, 100),
        "group": "SNOW-Integration",
    },
]

def connect():
    return psycopg2.connect(**DB)

def exec_sql(cur, sql, args=None):
    cur.execute(sql, args or ())

def ensure_schema(cur):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        cur.execute(f.read())

def seed_users(cur, n=80):
    cur.execute("SELECT count(*) FROM seip_users")
    if cur.fetchone()[0] >= n:
        return
    for _ in range(n):
        first, last = fake.first_name(), fake.last_name()
        name = f"{first} {last}"
        email = f"{first}.{last}.{random.randint(1000,9999)}@seip.local".lower()
        dept = random.choice(["IT Operations", "Application Support", "Infrastructure", "Platform Engineering", "Service Management"])
        location = random.choice(["Pune", "Mumbai", "Bengaluru", "Oslo", "London", "Frankfurt", "New York"])
        role = random.choice(["Resolver", "Senior Resolver", "Service Desk", "Change Manager", "Problem Manager", "Platform Admin"])
        cur.execute(
            """INSERT INTO seip_users(user_name,email,department,location,role)
               VALUES(%s,%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING""",
            (name, email, dept, location, role),
        )

def seed_cis(cur, n=120):
    cur.execute("SELECT count(*) FROM cmdb_ci")
    if cur.fetchone()[0] >= n:
        return
    existing = cur.fetchone()
    for i in range(n):
        p = random.choice(PATTERNS)
        prefix = p["tech"].upper().replace(" ", "")[:8]
        name = f"{prefix}-{random.choice(['APP','DB','SRV','NET'])}-{i+1:04d}"
        ci_type = random.choice(["Server", "Database", "Application", "Network Device", "Service"])
        env = random.choices(["Production", "UAT", "Development"], weights=[70,20,10])[0]
        os_platform = "RHEL 9" if p["tech"] in ["RedHat", "Unix"] else random.choice(["PostgreSQL 17", "NetworkOS", "ServiceNow"])
        service = p["service"]
        owner = p["group"]
        cur.execute(
            """INSERT INTO cmdb_ci(ci_name,ci_type,environment,os_platform,application_name,
               service_name,ip_address,criticality,owner_group)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(ci_name) DO NOTHING""",
            (name, ci_type, env, os_platform, fake.bs()[:80], service,
             f"10.{random.randint(10,200)}.{random.randint(1,254)}.{random.randint(1,254)}",
             random.choice(["Low","Medium","High","Critical"]), owner)
        )

def seed_runbooks(cur):
    cur.execute("SELECT count(*) FROM runbooks")
    if cur.fetchone()[0] > 0:
        return
    for i, p in enumerate(PATTERNS, 1):
        cur.execute(
            """INSERT INTO runbooks(runbook_number,title,category,technology,trigger_signature,purpose,
               steps,rollback_steps,estimated_minutes,automation_level,owner_group,success_rate)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                f"RB{1000+i}",
                f"{p['tech']} - {p['symptom'].title()}",
                p["category"], p["tech"], p["symptom"], p["runbook"],
                Json([p["runbook"], "Collect evidence and record result", "Validate service health", "Close or escalate"]),
                Json(["Restore previous configuration if changed", "Escalate to L3 if validation fails"]),
                random.randint(10,45),
                random.choice(["Manual", "Semi-Automated", "Automated"]),
                p["group"], round(random.uniform(82, 99), 2)
            )
        )

def get_ids(cur, table, id_col):
    cur.execute(f"SELECT {id_col} FROM {table}")
    return [r[0] for r in cur.fetchall()]

def create_problems(cur):
    cur.execute("SELECT problem_number FROM problem_records")
    existing = {r[0] for r in cur.fetchall()}
    problems = {}
    for p in PATTERNS:
        number = "PRB" + str(abs(hash(p["id"])) % 900000 + 100000)
        if number in existing:
            cur.execute("SELECT problem_id FROM problem_records WHERE problem_number=%s", (number,))
        else:
            ci_ids = get_ids(cur, "cmdb_ci", "ci_id")
            ci_id = random.choice(ci_ids)
            cur.execute(
                """INSERT INTO problem_records(problem_number,short_description,category,subcategory,
                   root_cause,known_error,workaround,status,priority,assignment_group,ci_id,first_detected_at)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING problem_id""",
                (number, f"Recurring {p['symptom']}", p["category"], p["subcategory"], p["root"],
                 True, p["runbook"], "Known Error", "P2", p["group"], ci_id,
                 datetime.now(timezone.utc) - timedelta(days=random.randint(10,180)))
            )
        problems[p["id"]] = cur.fetchone()[0]
    return problems

def get_reference_data(cur):
    users = get_ids(cur, "seip_users", "user_id")
    cis = get_ids(cur, "cmdb_ci", "ci_id")
    runbooks = {}
    cur.execute("SELECT runbook_id, trigger_signature FROM runbooks")
    for rid, sig in cur.fetchall():
        runbooks[sig] = rid
    return users, cis, runbooks

def make_incident(cur, seq, base_time, users, cis, runbooks, problems):
    p = random.choice(PATTERNS)
    opened = base_time - timedelta(minutes=random.randint(0, 1440))
    impact = random.choice([1,2,2,3])
    urgency = random.choice([1,2,2,3])
    priority = "P1" if impact == 1 and urgency == 1 else "P2" if impact <= 2 and urgency <= 2 else "P3"
    resolved = opened + timedelta(minutes=random.randint(15, 480))
    closed = resolved + timedelta(minutes=random.randint(5, 240))
    ci_id = random.choice(cis)
    caller = random.choice(users)
    resolver = random.choice(users)
    rb_id = runbooks.get(p["symptom"])
    problem_id = problems.get(p["id"])
    inc_no = unique_number("INC")
    desc = f"{p['desc']}. Initial symptom: {p['symptom']}."
    ai_conf = round(random.uniform(86, 99.7), 2)
    cur.execute(
        """INSERT INTO incidents(incident_number,opened_at,resolved_at,closed_at,caller_id,category,
           subcategory,service,short_description,description,impact,urgency,priority,state,
           assignment_group,assigned_to,ci_id,problem_id,runbook_id,source,symptom_signature,
           normalized_pattern_id,ai_candidate,ai_confidence)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Closed',%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)
           RETURNING incident_id""",
        (inc_no, opened, resolved, closed, caller, p["category"], p["subcategory"], p["service"],
         p["symptom"].title(), desc, impact, urgency, priority, p["group"], resolver, ci_id,
         problem_id, rb_id, random.choice(["Monitoring", "Email", "Service Desk", "API", "Phone"]),
         p["symptom"], p["id"], ai_conf)
    )
    incident_id = cur.fetchone()[0]

    # 1-3 alerts before/around the incident
    for a in range(random.randint(1,3)):
        metric, value, threshold = p["metric"]
        cur.execute(
            """INSERT INTO alerts(alert_number,alert_time,source,monitoring_tool,alert_type,severity,
               metric_name,metric_value,threshold_value,message,ci_id,incident_id,normalized_pattern_id)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (unique_number("ALT"),
             opened - timedelta(minutes=random.randint(1,30)),
             "Monitoring", random.choice(["Dynatrace","Prometheus","Zabbix","ServiceNow Event Mgmt"]),
             p["symptom"], "Critical" if priority == "P1" else "Warning",
             metric, value * random.uniform(0.85,1.15), threshold,
             f"{p['symptom']} detected on CI", ci_id, incident_id, p["id"])
        )

    # Resolver history = the operational trail your agents can learn from
    actions = [
        ("Triage", "Validated alert and reproduced the reported symptom"),
        ("Evidence Collection", "Collected logs, metrics and current service state"),
        ("Diagnosis", p["root"]),
        ("Remediation", p["runbook"]),
        ("Validation", "Service health returned to normal and monitoring was stable"),
    ]
    for idx, (atype, detail) in enumerate(actions, 1):
        event_time = opened + timedelta(minutes=idx * random.randint(3,15))
        cur.execute(
            """INSERT INTO resolver_history(incident_id,event_time,resolver_id,action_type,
               action_details,evidence,result,next_action,duration_minutes,normalized_pattern_id)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (incident_id, event_time, resolver, atype, detail,
             f"{p['metric'][0]} crossed threshold {p['metric'][2]}",
             "Successful" if idx >= 4 else "Observed",
             "Monitor for recurrence" if idx == 5 else "Continue investigation",
             random.randint(3,25), p["id"])
        )

    return incident_id, p

def create_change_for_pattern(cur, seq, base_time, users, cis, problem_id, p):
    requested = base_time - timedelta(days=random.randint(0,30))
    start = requested + timedelta(hours=random.randint(2,72))
    end = start + timedelta(hours=random.randint(1,4))
    ch_no = unique_number("CHG")
    cur.execute(
        """INSERT INTO changes(change_number,requested_at,planned_start,planned_end,completed_at,
           change_type,risk,impact,state,short_description,implementation_plan,backout_plan,
           assignment_group,requested_by,ci_id,related_problem_id,normalized_pattern_id)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'Closed',%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING change_id""",
        (ch_no, requested, start, end, end + timedelta(minutes=random.randint(5,60)),
         random.choice(["Standard","Normal","Emergency"]), random.choice(["Low","Medium","High"]),
         random.choice(["Low","Medium","High"]), f"Remediation change for {p['symptom']}",
         p["runbook"], "Restore previous configuration and validate service",
         p["group"], random.choice(users), random.choice(cis), problem_id, p["id"])
    )
    change_id = cur.fetchone()[0]

    for task_idx, task_type in enumerate(["Pre-check", "Implementation", "Validation"], 1):
        task_no = unique_number("CTASK")
        cur.execute(
            """INSERT INTO change_tasks(task_number,change_id,task_type,sequence_no,short_description,
               assignment_group,assigned_to,state,planned_start,planned_end,completed_at,task_result,
               normalized_pattern_id)
               VALUES(%s,%s,%s,%s,%s,%s,%s,'Closed',%s,%s,%s,%s,%s)
               RETURNING change_task_id""",
            (task_no, change_id, task_type, task_idx,
             f"{task_type}: {p['symptom']}", p["group"], random.choice(users),
             start + timedelta(minutes=(task_idx-1)*30),
             start + timedelta(minutes=task_idx*30),
             start + timedelta(minutes=task_idx*30+random.randint(2,10)),
             "Completed successfully", p["id"])
        )
        task_id = cur.fetchone()[0]
        cur.execute(
            """INSERT INTO resolver_history(change_task_id,event_time,resolver_id,action_type,
               action_details,evidence,result,next_action,duration_minutes,normalized_pattern_id)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (task_id, start + timedelta(minutes=task_idx*30), random.choice(users),
             "Change Task Execution", f"Executed {task_type.lower()} for recurring pattern",
             "Pre/post validation evidence captured", "Successful",
             "Proceed to next change task" if task_idx < 3 else "Close task",
             random.randint(5,30), p["id"])
        )

    # Approval workflow
    for level in [1,2]:
        cur.execute(
            """INSERT INTO approval_history(approval_number,object_type,object_id,approver_id,
               approval_level,state,comments,requested_at,decided_at)
               VALUES(%s,'CHANGE',%s,%s,%s,'Approved',%s,%s,%s)""",
            (unique_number("APR"), change_id,
             random.choice(users), level,
             "Approved after risk and implementation review",
             requested - timedelta(hours=level), requested - timedelta(hours=level-1))
        )

    return change_id

def generate(n_incidents=200, days_back=1):
    conn = connect()
    conn.autocommit = False
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        seed_users(cur)
        seed_cis(cur)
        seed_runbooks(cur)
        problems = create_problems(cur)
        users, cis, runbooks = get_reference_data(cur)

        base = datetime.now(timezone.utc) - timedelta(days=days_back-1)
        for i in range(1, n_incidents+1):
            incident_id, p = make_incident(
                cur, i, base - timedelta(minutes=random.randint(0, 1439)),
                users, cis, runbooks, problems
            )
            # Around 25% of incidents generate a change, creating the history
            # needed for change recommendation and recurrence analysis.
            if random.random() < 0.25:
                create_change_for_pattern(
                    cur, i, base, users, cis, problems[p["id"]], p
                )

        conn.commit()
        print(f"Generated {n_incidents} incidents plus related alerts/resolver history.")
        print("Approximately 25% also received changes, change tasks and approvals.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--incidents", type=int, default=200)
    parser.add_argument("--days-back", type=int, default=1)
    args = parser.parse_args()
    generate(args.incidents, args.days_back)
