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
            ('EVIDENCE_BUILD', 'RUNNING')
        RETURNING run_id
        """
    )
    return cur.fetchone()[0]


def insert_evidence(cur, rows):
    if not rows:
        return 0

    cur.executemany(
        """
        INSERT INTO seip_evidence (
            source_table,
            source_record_id,
            evidence_type,
            event_time,
            service_name,
            ci_id,
            pattern_id,
            actor_id,
            assignment_group,
            title,
            description,
            evidence_confidence,
            evidence_quality
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (source_table, source_record_id, evidence_type)
        DO UPDATE SET
            event_time = EXCLUDED.event_time,
            service_name = EXCLUDED.service_name,
            ci_id = EXCLUDED.ci_id,
            pattern_id = EXCLUDED.pattern_id,
            actor_id = EXCLUDED.actor_id,
            assignment_group = EXCLUDED.assignment_group,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            evidence_confidence = EXCLUDED.evidence_confidence,
            evidence_quality = EXCLUDED.evidence_quality
        """,
        rows,
    )

    return len(rows)


def build_incident_evidence(cur):
    cur.execute(
        """
        SELECT
            incident_id,
            opened_at,
            service,
            ci_id,
            normalized_pattern_id,
            assigned_to,
            assignment_group,
            short_description,
            description,
            ai_confidence
        FROM incidents
        """
    )

    rows = []

    for r in cur.fetchall():
        (
            incident_id,
            event_time,
            service_name,
            ci_id,
            pattern_id,
            actor_id,
            assignment_group,
            title,
            description,
            confidence,
        ) = r

        rows.append(
            (
                "incidents",
                incident_id,
                "INCIDENT",
                event_time,
                service_name,
                ci_id,
                pattern_id,
                actor_id,
                assignment_group,
                title,
                description,
                confidence,
                "VALID",
            )
        )

    return insert_evidence(cur, rows)


def build_alert_evidence(cur):
    cur.execute(
        """
        SELECT
            alert_id,
            alert_time,
            ci_id,
            normalized_pattern_id,
            alert_type,
            message,
            severity
        FROM alerts
        """
    )

    rows = []

    for r in cur.fetchall():
        (
            alert_id,
            event_time,
            ci_id,
            pattern_id,
            alert_type,
            message,
            severity,
        ) = r

        rows.append(
            (
                "alerts",
                alert_id,
                "ALERT",
                event_time,
                None,
                ci_id,
                pattern_id,
                None,
                None,
                alert_type,
                message,
                None,
                "VALID",
            )
        )

    return insert_evidence(cur, rows)


def build_change_evidence(cur):
    cur.execute(
        """
        SELECT
            change_id,
            requested_at,
            ci_id,
            normalized_pattern_id,
            requested_by,
            assignment_group,
            short_description,
            implementation_plan
        FROM changes
        """
    )

    rows = []

    for r in cur.fetchall():
        (
            change_id,
            event_time,
            ci_id,
            pattern_id,
            actor_id,
            assignment_group,
            title,
            description,
        ) = r

        rows.append(
            (
                "changes",
                change_id,
                "CHANGE",
                event_time,
                None,
                ci_id,
                pattern_id,
                actor_id,
                assignment_group,
                title,
                description,
                None,
                "VALID",
            )
        )

    return insert_evidence(cur, rows)


def build_change_task_evidence(cur):
    cur.execute(
        """
        SELECT
            change_task_id,
            completed_at,
            assigned_to,
            assignment_group,
            short_description,
            task_result,
            normalized_pattern_id
        FROM change_tasks
        WHERE completed_at IS NOT NULL
        """
    )

    rows = []

    for r in cur.fetchall():
        (
            task_id,
            event_time,
            actor_id,
            assignment_group,
            title,
            description,
            pattern_id,
        ) = r

        rows.append(
            (
                "change_tasks",
                task_id,
                "CHANGE_TASK",
                event_time,
                None,
                None,
                pattern_id,
                actor_id,
                assignment_group,
                title,
                description,
                None,
                "VALID",
            )
        )

    return insert_evidence(cur, rows)


def build_resolver_evidence(cur):
    cur.execute(
        """
        SELECT
            history_id,
            event_time,
            resolver_id,
            action_type,
            action_details,
            evidence,
            normalized_pattern_id
        FROM resolver_history
        """
    )

    rows = []

    for r in cur.fetchall():
        (
            history_id,
            event_time,
            actor_id,
            action_type,
            action_details,
            evidence,
            pattern_id,
        ) = r

        description = action_details

        if evidence:
            description = f"{action_details}. Evidence: {evidence}"

        rows.append(
            (
                "resolver_history",
                history_id,
                "RESOLVER_ACTION",
                event_time,
                None,
                None,
                pattern_id,
                actor_id,
                None,
                action_type,
                description,
                None,
                "VALID",
            )
        )

    return insert_evidence(cur, rows)


def build_problem_evidence(cur):
    cur.execute(
        """
        SELECT
            problem_id,
            first_detected_at,
            ci_id,
            assignment_group,
            short_description,
            root_cause,
            priority
        FROM problem_records
        WHERE first_detected_at IS NOT NULL
        """
    )

    rows = []

    for r in cur.fetchall():
        (
            problem_id,
            event_time,
            ci_id,
            assignment_group,
            title,
            description,
            priority,
        ) = r

        rows.append(
            (
                "problem_records",
                problem_id,
                "PROBLEM",
                event_time,
                None,
                ci_id,
                None,
                None,
                assignment_group,
                title,
                description,
                None,
                "VALID",
            )
        )

    return insert_evidence(cur, rows)


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

    try:
        cur = conn.cursor()

        run_id = get_run_id(cur)

        total = 0
        counts = {}

        builders = [
            ("incidents", build_incident_evidence),
            ("alerts", build_alert_evidence),
            ("changes", build_change_evidence),
            ("change_tasks", build_change_task_evidence),
            ("resolver_history", build_resolver_evidence),
            ("problem_records", build_problem_evidence),
        ]

        for name, builder in builders:
            count = builder(cur)
            counts[name] = count
            total += count

        update_run(
            cur,
            run_id,
            "COMPLETED",
            total,
            total,
        )

        conn.commit()

        print("\nSEIP Evidence Build Completed")
        print("--------------------------------")
        for name, count in counts.items():
            print(f"{name:20} : {count}")
        print("--------------------------------")
        print(f"Total evidence       : {total}")
        print(f"Processing run       : {run_id}")

    except Exception as exc:
        conn.rollback()

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
