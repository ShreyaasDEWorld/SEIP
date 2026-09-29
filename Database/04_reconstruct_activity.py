import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DB = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "seip_itsm"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

ACTION_MAP = {
    "Triage": "TRIAGE",
    "Evidence Collection": "EVIDENCE_COLLECTION",
    "Diagnosis": "DIAGNOSIS",
    "Remediation": "REMEDIATION",
    "Validation": "VALIDATION",
}

def connect():
    return psycopg2.connect(**DB)

def start_run(cur):
    cur.execute("""
        INSERT INTO seip_processing_runs (run_type, started_at, status)
        VALUES ('ACTIVITY_RECONSTRUCTION', now(), 'RUNNING')
        RETURNING run_id
    """)
    return cur.fetchone()[0]

def finish_run(cur, run_id, read_count, created_count, error_count=0, error_message=None):
    cur.execute("""
        UPDATE seip_processing_runs
        SET completed_at = now(),
            status = %s,
            records_read = %s,
            records_created = %s,
            error_count = %s,
            error_message = %s
        WHERE run_id = %s
    """, (
        "COMPLETED" if error_count == 0 else "FAILED",
        read_count, created_count, error_count, error_message, run_id
    ))

def find_correlation(cur, pattern_id, service_name, ci_id):
    cur.execute("""
        SELECT correlation_id
        FROM seip_correlation_group
        WHERE pattern_id = %s
          AND service_name = %s
          AND ci_id IS NOT DISTINCT FROM %s
        LIMIT 1
    """, (pattern_id, service_name, ci_id))
    row = cur.fetchone()
    return row[0] if row else None

def reconstruct():
    conn = connect()
    conn.autocommit = False

    try:
        cur = conn.cursor()
        run_id = start_run(cur)

        # Rebuild target so the script can be safely rerun.
        cur.execute("DELETE FROM seip_activity")

        # Incident resolver history -> operational activities.
        cur.execute("""
            SELECT
                rh.history_id,
                rh.event_time,
                rh.resolver_id,
                rh.action_type,
                rh.action_details,
                rh.result,
                COALESCE(rh.duration_minutes, 0),
                rh.normalized_pattern_id,
                i.service,
                i.ci_id,
                i.assignment_group
            FROM resolver_history rh
            JOIN incidents i ON i.incident_id = rh.incident_id
            WHERE rh.incident_id IS NOT NULL
            ORDER BY rh.event_time, rh.history_id
        """)
        incident_rows = cur.fetchall()

        # Change-task resolver history -> change execution activities.
        cur.execute("""
            SELECT
                rh.history_id,
                rh.event_time,
                rh.resolver_id,
                rh.action_details,
                rh.result,
                COALESCE(rh.duration_minutes, 0),
                rh.normalized_pattern_id,
                c.ci_id,
                c.assignment_group,
                c.change_number,
                ct.task_type
            FROM resolver_history rh
            JOIN change_tasks ct ON ct.change_task_id = rh.change_task_id
            JOIN changes c ON c.change_id = ct.change_id
            WHERE rh.change_task_id IS NOT NULL
            ORDER BY rh.event_time, rh.history_id
        """)
        change_rows = cur.fetchall()

        total_read = len(incident_rows) + len(change_rows)
        created = 0
        skipped = 0

        for row in incident_rows:
            (
                history_id, event_time, resolver_id, action_type,
                details, result, duration, pattern_id,
                service_name, ci_id, assignment_group
            ) = row

            activity_type = ACTION_MAP.get(action_type)
            if not activity_type:
                skipped += 1
                continue

            correlation_id = find_correlation(
                cur, pattern_id, service_name, ci_id
            )
            if correlation_id is None:
                skipped += 1
                continue

            cur.execute("""
                SELECT %s::timestamptz + (%s * INTERVAL '1 minute')
            """, (event_time, duration))
            end_time = cur.fetchone()[0]

            reason = (
                f"Resolver history #{history_id}: "
                f"{details or action_type}. "
                f"Result: {result or 'N/A'}."
            )

            cur.execute("""
                INSERT INTO seip_activity (
                    correlation_id, service_name, ci_id, pattern_id,
                    activity_type, start_time, end_time, actor_id,
                    assignment_group, duration_minutes, evidence_count,
                    classification, classification_reason,
                    classification_confidence
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,
                    'UNCLASSIFIED',%s,100
                )
            """, (
                correlation_id, service_name, ci_id, pattern_id,
                activity_type, event_time, end_time, resolver_id,
                assignment_group, duration, reason
            ))
            created += 1

        for row in change_rows:
            (
                history_id, event_time, resolver_id, details,
                result, duration, pattern_id, ci_id,
                assignment_group, change_number, task_type
            ) = row

            cur.execute("""
                SELECT service_name
                FROM cmdb_ci
                WHERE ci_id = %s
            """, (ci_id,))
            service_row = cur.fetchone()
            service_name = service_row[0] if service_row else "UNKNOWN_SERVICE"

            correlation_id = find_correlation(
                cur, pattern_id, service_name, ci_id
            )
            if correlation_id is None:
                skipped += 1
                continue

            cur.execute("""
                SELECT %s::timestamptz + (%s * INTERVAL '1 minute')
            """, (event_time, duration))
            end_time = cur.fetchone()[0]

            reason = (
                f"Change {change_number}, task {task_type}: "
                f"{details or 'Change task execution'}. "
                f"Result: {result or 'N/A'}."
            )

            cur.execute("""
                INSERT INTO seip_activity (
                    correlation_id, service_name, ci_id, pattern_id,
                    activity_type, start_time, end_time, actor_id,
                    assignment_group, duration_minutes, evidence_count,
                    classification, classification_reason,
                    classification_confidence
                )
                VALUES (
                    %s,%s,%s,%s,'CHANGE_EXECUTION',%s,%s,%s,%s,%s,1,
                    'UNCLASSIFIED',%s,100
                )
            """, (
                correlation_id, service_name, ci_id, pattern_id,
                event_time, end_time, resolver_id,
                assignment_group, duration, reason
            ))
            created += 1

        cur.execute("""
            UPDATE seip_processing_runs
            SET metadata = jsonb_build_object(
                'skipped_records', %s,
                'incident_history_records', %s,
                'change_history_records', %s
            )
            WHERE run_id = %s
        """, (skipped, len(incident_rows), len(change_rows), run_id))

        finish_run(cur, run_id, total_read, created)
        conn.commit()

        print("SEIP Activity Reconstruction Completed")
        print("--------------------------------")
        print(f"Incident history records : {len(incident_rows)}")
        print(f"Change history records   : {len(change_rows)}")
        print(f"Activities created       : {created}")
        print(f"Records skipped          : {skipped}")
        print(f"Processing run           : {run_id}")

    except Exception as exc:
        conn.rollback()
        try:
            cur.execute("""
                UPDATE seip_processing_runs
                SET completed_at = now(),
                    status = 'FAILED',
                    error_count = 1,
                    error_message = %s
                WHERE run_id = %s
            """, (str(exc), run_id))
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    reconstruct()
