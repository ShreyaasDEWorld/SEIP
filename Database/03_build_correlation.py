import os
import psycopg2
from dotenv import load_dotenv

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


def get_run_id(cur):
    cur.execute(
        """
        INSERT INTO seip_processing_runs
            (run_type, status)
        VALUES
            ('CORRELATION_BUILD', 'RUNNING')
        RETURNING run_id
        """
    )
    return cur.fetchone()[0]


def build_correlations(cur):
    """
    Phase 1 correlation strategy:

    Primary:
        pattern_id

    Secondary:
        service_name / CI

    The current generator deliberately propagates normalized_pattern_id
    across the operational records, so this is the strongest available
    Phase 1 correlation key.
    """

    cur.execute(
        """
        SELECT
            COALESCE(pattern_id, 'NO_PATTERN') AS pattern_id,
            COALESCE(service_name, 'UNKNOWN_SERVICE') AS service_name,
            ci_id,
            MIN(event_time) AS first_event_time,
            MAX(event_time) AS last_event_time,
            COUNT(*) AS evidence_count
        FROM seip_evidence
        GROUP BY
            COALESCE(pattern_id, 'NO_PATTERN'),
            COALESCE(service_name, 'UNKNOWN_SERVICE'),
            ci_id
        ORDER BY
            first_event_time
        """
    )

    groups = cur.fetchall()

    created = 0

    for (
        pattern_id,
        service_name,
        ci_id,
        first_event_time,
        last_event_time,
        evidence_count,
    ) in groups:

        correlation_key = (
            f"{pattern_id}|{service_name}|"
            f"{ci_id if ci_id is not None else 'NO_CI'}"
        )

        cur.execute(
            """
            INSERT INTO seip_correlation_group (
                correlation_key,
                pattern_id,
                service_name,
                ci_id,
                first_event_time,
                last_event_time,
                evidence_count,
                correlation_method,
                correlation_confidence,
                status
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                'PATTERN_SERVICE_CI',
                %s,
                'ACTIVE'
            )
            ON CONFLICT (correlation_key)
            DO UPDATE SET
                first_event_time = EXCLUDED.first_event_time,
                last_event_time = EXCLUDED.last_event_time,
                evidence_count = EXCLUDED.evidence_count,
                correlation_confidence = EXCLUDED.correlation_confidence,
                updated_at = now()
            RETURNING correlation_id
            """,
            (
                correlation_key,
                None if pattern_id == "NO_PATTERN" else pattern_id,
                None if service_name == "UNKNOWN_SERVICE" else service_name,
                ci_id,
                first_event_time,
                last_event_time,
                evidence_count,
                100.00 if pattern_id != "NO_PATTERN" else 60.00,
            ),
        )

        cur.fetchone()
        created += 1

    return created


def link_evidence(cur):
    """
    Link every evidence record to its correlation group.
    """

    cur.execute(
        """
        INSERT INTO seip_correlation_evidence (
            correlation_id,
            evidence_id,
            relationship_type,
            relationship_confidence
        )
        SELECT
            cg.correlation_id,
            e.evidence_id,
            'PATTERN_SERVICE_CI',
            cg.correlation_confidence
        FROM seip_evidence e
        JOIN seip_correlation_group cg
          ON COALESCE(e.pattern_id, 'NO_PATTERN')
             = COALESCE(cg.pattern_id, 'NO_PATTERN')
         AND COALESCE(e.service_name, 'UNKNOWN_SERVICE')
             = COALESCE(cg.service_name, 'UNKNOWN_SERVICE')
         AND COALESCE(e.ci_id, -1)
             = COALESCE(cg.ci_id, -1)
        ON CONFLICT (correlation_id, evidence_id)
        DO NOTHING
        """
    )

    return cur.rowcount


def update_run(cur, run_id, status, records_read, records_created):
    cur.execute(
        """
        UPDATE seip_processing_runs
        SET
            completed_at = now(),
            status = %s,
            records_read = %s,
            records_created = %s
        WHERE run_id = %s
        """,
        (status, records_read, records_created, run_id),
    )


def main():
    conn = connect()
    conn.autocommit = False

    run_id = None

    try:
        cur = conn.cursor()

        run_id = get_run_id(cur)

        cur.execute("SELECT COUNT(*) FROM seip_evidence")
        evidence_count = cur.fetchone()[0]

        if evidence_count == 0:
            raise RuntimeError(
                "No evidence found. Run 02_build_evidence.py first."
            )

        correlation_count = build_correlations(cur)
        link_count = link_evidence(cur)

        update_run(
            cur,
            run_id,
            "COMPLETED",
            evidence_count,
            correlation_count,
        )

        conn.commit()

        print("\nSEIP Correlation Build Completed")
        print("--------------------------------")
        print(f"Evidence records     : {evidence_count}")
        print(f"Correlation groups   : {correlation_count}")
        print(f"Evidence links       : {link_count}")
        print(f"Processing run       : {run_id}")

    except Exception as exc:
        conn.rollback()

        if run_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE seip_processing_runs
                    SET
                        completed_at = now(),
                        status = 'FAILED',
                        error_count = 1,
                        error_message = %s
                    WHERE run_id = %s
                    """,
                    (str(exc), run_id),
                )
                conn.commit()
            except Exception:
                pass

        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
