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

def build_reviewer_queue():
    conn = connect()
    conn.autocommit = False

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO seip_processing_runs (run_type, started_at, status)
            VALUES ('REVIEW_QUEUE_BUILD', now(), 'RUNNING')
            RETURNING run_id
        """)
        run_id = cur.fetchone()[0]

        cur.execute("DELETE FROM seip_review_queue")

        cur.execute("""
            SELECT
                leakage_id,
                activity_count,
                estimated_minutes,
                confidence,
                explanation
            FROM seip_capacity_leakage
            WHERE status = 'OPEN'
            ORDER BY
                CASE
                    WHEN confidence < 80 THEN 1
                    WHEN estimated_minutes >= 120 THEN 2
                    WHEN activity_count >= 5 THEN 3
                    ELSE 4
                END,
                estimated_minutes DESC,
                leakage_id
        """)
        rows = cur.fetchall()
        created = 0

        for row in rows:
            (
                leakage_id,
                activity_count,
                estimated_minutes,
                confidence,
                explanation
            ) = row

            if confidence < 80:
                priority = "HIGH"
                reason = "Low correlation confidence requires human validation."
            elif estimated_minutes >= 120:
                priority = "HIGH"
                reason = "High recorded operational effort requires reviewer assessment."
            elif activity_count >= 5:
                priority = "MEDIUM"
                reason = "Repeated activity pattern requires reviewer assessment."
            else:
                priority = "LOW"
                reason = "Evidence-backed activity surfaced for reviewer confirmation."

            cur.execute("""
                INSERT INTO seip_review_queue (
                    object_type, object_id, priority, reason,
                    confidence, status
                )
                VALUES (
                    'CAPACITY_LEAKAGE', %s, %s, %s, %s, 'OPEN'
                )
            """, (
                leakage_id,
                priority,
                f"{reason} {explanation}",
                confidence
            ))
            created += 1

        cur.execute("""
            UPDATE seip_processing_runs
            SET completed_at = now(),
                status = 'COMPLETED',
                records_read = %s,
                records_created = %s,
                metadata = jsonb_build_object(
                    'queue_status', 'OPEN',
                    'human_review_required', true
                )
            WHERE run_id = %s
        """, (len(rows), created, run_id))

        conn.commit()

        print("SEIP Reviewer Queue Build Completed")
        print("--------------------------------")
        print(f"Leakage records read : {len(rows)}")
        print(f"Review items created : {created}")
        print(f"Processing run       : {run_id}")

        print("\nReviewer Queue Summary")
        cur.execute("""
            SELECT priority, COUNT(*)
            FROM seip_review_queue
            GROUP BY priority
            ORDER BY
                CASE priority
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    ELSE 3
                END
        """)
        for priority, count in cur.fetchall():
            print(f"{priority:8} : {count}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    build_reviewer_queue()
