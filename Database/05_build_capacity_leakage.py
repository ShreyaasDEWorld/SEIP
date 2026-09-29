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

def connect():
    return psycopg2.connect(**DB)

def build_leakage():
    conn = connect()
    conn.autocommit = False

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO seip_processing_runs (run_type, started_at, status)
            VALUES ('CAPACITY_LEAKAGE', now(), 'RUNNING')
            RETURNING run_id
        """)
        run_id = cur.fetchone()[0]

        cur.execute("DELETE FROM seip_capacity_leakage")

        # One row per correlation group. All measures come from reconstructed
        # activity; evidence_count comes from the correlation group.
        cur.execute("""
            SELECT
                cg.correlation_id,
                cg.service_name,
                cg.pattern_id,
                cg.correlation_confidence,
                cg.evidence_count,
                COUNT(sa.activity_id) AS activity_count,
                COALESCE(SUM(sa.duration_minutes), 0) AS total_minutes,
                COALESCE(SUM(
                    CASE WHEN sa.activity_type = 'DIAGNOSIS'
                         THEN sa.duration_minutes ELSE 0 END
                ), 0) AS diagnosis_minutes,
                COALESCE(SUM(
                    CASE WHEN sa.activity_type = 'REMEDIATION'
                         THEN sa.duration_minutes ELSE 0 END
                ), 0) AS remediation_minutes,
                COALESCE(SUM(
                    CASE WHEN sa.activity_type = 'CHANGE_EXECUTION'
                         THEN sa.duration_minutes ELSE 0 END
                ), 0) AS change_minutes
            FROM seip_correlation_group cg
            JOIN seip_activity sa
              ON sa.correlation_id = cg.correlation_id
            GROUP BY
                cg.correlation_id,
                cg.service_name,
                cg.pattern_id,
                cg.correlation_confidence,
                cg.evidence_count
            ORDER BY cg.correlation_id
        """)

        rows = cur.fetchall()
        created = 0

        for row in rows:
            (
                correlation_id, service_name, pattern_id,
                corr_confidence, evidence_count,
                activity_count, total_minutes,
                diagnosis_minutes, remediation_minutes,
                change_minutes
            ) = row

            if change_minutes > 0:
                leakage_type = "CHANGE_OVERHEAD"
                explanation = (
                    f"Recorded change execution accounts for "
                    f"{change_minutes} minutes of operational activity."
                )
            elif remediation_minutes > 0:
                leakage_type = "REACTIVE_REMEDIATION"
                explanation = (
                    f"Recorded remediation accounts for "
                    f"{remediation_minutes} minutes of operational activity."
                )
            elif diagnosis_minutes > 0:
                leakage_type = "MANUAL_DIAGNOSIS"
                explanation = (
                    f"Recorded diagnosis accounts for "
                    f"{diagnosis_minutes} minutes of operational activity."
                )
            else:
                leakage_type = "OPERATIONAL_RESPONSE"
                explanation = (
                    f"Recorded operational response totals "
                    f"{total_minutes} minutes."
                )

            confidence = min(
                100.0,
                max(60.0, float(corr_confidence or 60.0))
            )

            cur.execute("""
                INSERT INTO seip_capacity_leakage (
                    correlation_id, service_name, pattern_id,
                    leakage_type, activity_count, estimated_minutes,
                    estimated_hours, evidence_count, confidence,
                    explanation, status
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPEN'
                )
            """, (
                correlation_id,
                service_name,
                pattern_id,
                leakage_type,
                activity_count,
                total_minutes,
                round(total_minutes / 60.0, 2),
                evidence_count,
                round(confidence, 2),
                explanation
            ))
            created += 1

        cur.execute("""
            UPDATE seip_processing_runs
            SET completed_at = now(),
                status = 'COMPLETED',
                records_read = %s,
                records_created = %s,
                metadata = jsonb_build_object(
                    'rule_based', true,
                    'source', 'seip_activity'
                )
            WHERE run_id = %s
        """, (len(rows), created, run_id))

        conn.commit()

        print("SEIP Capacity Leakage Build Completed")
        print("--------------------------------")
        print(f"Correlation groups read : {len(rows)}")
        print(f"Leakage records created : {created}")
        print(f"Processing run          : {run_id}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    build_leakage()
