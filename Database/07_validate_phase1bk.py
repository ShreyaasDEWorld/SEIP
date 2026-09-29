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


def run_validation():
    conn = connect()
    conn.autocommit = False

    try:
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO seip_processing_runs (run_type, started_at, status)
            VALUES ('PHASE1_VALIDATION', now(), 'RUNNING')
            RETURNING run_id
        """)
        run_id = cur.fetchone()[0]

        checks = []

        # ------------------------------------------------------------
        # 1. Record counts
        # ------------------------------------------------------------
        count_sql = {
            "Source incidents": "SELECT COUNT(*) FROM incidents",
            "SEIP evidence": "SELECT COUNT(*) FROM seip_evidence",
            "Correlation groups": "SELECT COUNT(*) FROM seip_correlation_group",
            "Correlation evidence links": "SELECT COUNT(*) FROM seip_correlation_evidence",
            "SEIP activities": "SELECT COUNT(*) FROM seip_activity",
            "Capacity leakage": "SELECT COUNT(*) FROM seip_capacity_leakage",
            "Reviewer queue": "SELECT COUNT(*) FROM seip_review_queue",
        }

        counts = {}
        for name, sql in count_sql.items():
            cur.execute(sql)
            counts[name] = cur.fetchone()[0]

        # ------------------------------------------------------------
        # 2. Evidence lineage validation
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_correlation_evidence ce
            LEFT JOIN seip_evidence e
              ON e.evidence_id = ce.evidence_id
            WHERE e.evidence_id IS NULL
        """)
        orphan_correlation_evidence = cur.fetchone()[0]

        checks.append((
            "Correlation evidence lineage",
            orphan_correlation_evidence == 0,
            orphan_correlation_evidence
        ))

        # ------------------------------------------------------------
        # 3. Activity -> correlation lineage
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_activity a
            LEFT JOIN seip_correlation_group cg
              ON cg.correlation_id = a.correlation_id
            WHERE cg.correlation_id IS NULL
        """)
        orphan_activities = cur.fetchone()[0]

        checks.append((
            "Activity correlation lineage",
            orphan_activities == 0,
            orphan_activities
        ))

        # ------------------------------------------------------------
        # 4. Capacity leakage -> correlation lineage
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_capacity_leakage cl
            LEFT JOIN seip_correlation_group cg
              ON cg.correlation_id = cl.correlation_id
            WHERE cg.correlation_id IS NULL
        """)
        orphan_leakage = cur.fetchone()[0]

        checks.append((
            "Capacity leakage lineage",
            orphan_leakage == 0,
            orphan_leakage
        ))

        # ------------------------------------------------------------
        # 5. Reviewer queue -> leakage lineage
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_review_queue rq
            LEFT JOIN seip_capacity_leakage cl
              ON cl.leakage_id = rq.object_id
            WHERE rq.object_type = 'CAPACITY_LEAKAGE'
              AND cl.leakage_id IS NULL
        """)
        orphan_reviews = cur.fetchone()[0]

        checks.append((
            "Reviewer queue lineage",
            orphan_reviews == 0,
            orphan_reviews
        ))

        # ------------------------------------------------------------
        # 6. Activity quality checks
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_activity
            WHERE start_time IS NULL
               OR end_time IS NULL
               OR end_time < start_time
               OR duration_minutes < 0
        """)
        invalid_activities = cur.fetchone()[0]

        checks.append((
            "Activity timeline validity",
            invalid_activities == 0,
            invalid_activities
        ))

        # ------------------------------------------------------------
        # 7. Leakage quality checks
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_capacity_leakage
            WHERE estimated_minutes < 0
               OR estimated_hours < 0
               OR confidence < 0
               OR confidence > 100
        """)
        invalid_leakage = cur.fetchone()[0]

        checks.append((
            "Capacity leakage validity",
            invalid_leakage == 0,
            invalid_leakage
        ))

        # ------------------------------------------------------------
        # 8. Reviewer queue validity
        # ------------------------------------------------------------
        cur.execute("""
            SELECT COUNT(*)
            FROM seip_review_queue
            WHERE priority IS NULL
               OR status IS NULL
        """)
        invalid_reviews = cur.fetchone()[0]

        checks.append((
            "Reviewer queue validity",
            invalid_reviews == 0,
            invalid_reviews
        ))

        # ------------------------------------------------------------
        # 9. Processing runs
        # ------------------------------------------------------------
        cur.execute("""
            SELECT run_type, status, records_read, records_created
            FROM seip_processing_runs
            ORDER BY run_id
        """)
        processing_runs = cur.fetchall()

        failed_runs = [r for r in processing_runs if r[1] != "COMPLETED"]

        checks.append((
            "Processing runs",
            len(failed_runs) == 0,
            len(failed_runs)
        ))

        # ------------------------------------------------------------
        # 10. Overall validation
        # ------------------------------------------------------------
        passed = sum(1 for _, ok, _ in checks if ok)
        failed = len(checks) - passed
        overall_status = "PASSED" if failed == 0 else "FAILED"

        cur.execute("""
            UPDATE seip_processing_runs
            SET completed_at = now(),
                status = %s,
                records_read = %s,
                records_created = %s,
                error_count = %s,
                metadata = jsonb_build_object(
                    'checks_total', %s,
                    'checks_passed', %s,
                    'checks_failed', %s,
                    'phase', 'MVP_PHASE_1'
                )
            WHERE run_id = %s
        """, (
            overall_status,
            sum(counts.values()),
            passed,
            failed,
            len(checks),
            passed,
            failed,
            run_id
        ))

        conn.commit()

        # ------------------------------------------------------------
        # Output
        # ------------------------------------------------------------
        print("SEIP Phase 1 Validation")
        print("=======================")
        print()

        print("Record Counts")
        print("--------------------------------")
        for name, value in counts.items():
            print(f"{name:30} : {value}")

        print()
        print("Validation Checks")
        print("--------------------------------")

        for name, ok, value in checks:
            status = "PASS" if ok else "FAIL"
            print(f"{status:5} | {name:32} | {value}")

        print()
        print("Processing Runs")
        print("--------------------------------")
        for run_type, status, records_read, records_created in processing_runs:
            print(
                f"{run_type:25} | "
                f"{status:10} | "
                f"read={records_read or 0:<6} | "
                f"created={records_created or 0}"
            )

        print()
        print("--------------------------------")
        print(f"Checks passed : {passed}/{len(checks)}")
        print(f"Checks failed : {failed}")
        print(f"Overall status: {overall_status}")
        print(f"Processing run: {run_id}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_validation()
