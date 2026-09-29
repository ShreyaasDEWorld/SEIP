import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# Load .env from the dashboard folder first, then the project root.
# .env is kept in the project root, alongside this dashboard.
PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

st.set_page_config(
    page_title="SEIP — Phase 1 Reviewer Dashboard",
    page_icon="🔎",
    layout="wide",
)

# -------------------------------------------------------------------
# Database
# -------------------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "seip_itsm"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD"),
}


@st.cache_resource
def get_connection():
    if not DB_CONFIG["password"]:
        raise RuntimeError(
            "DB_PASSWORD is not set. Add DB_PASSWORD to the .env file "
            "used by the SEIP database scripts."
        )
    try:
        return psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as exc:
        raise RuntimeError(
            "PostgreSQL connection failed. The dashboard is using: "
            f"host={DB_CONFIG['host']}, port={DB_CONFIG['port']}, "
            f"database={DB_CONFIG['dbname']}, user={DB_CONFIG['user']}. "
            "Check the same DB credentials used by the SEIP database scripts."
        ) from exc


def query_df(sql, params=None):
    conn = get_connection()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise


# Verify the project .env was loaded without exposing credentials.
if not DB_CONFIG["password"]:
    st.error(
        f"PGPASSWORD was not found in {ENV_FILE}. "
        "Check the project-root .env file."
    )
    st.stop()

# -------------------------------------------------------------------
# Styling
# -------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    .metric-label {
        font-size: 0.85rem;
    }
    .section-title {
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------------------------
# Header
# -------------------------------------------------------------------
st.title("SEIP — Phase 1 Reviewer Dashboard")
st.caption(
    "Service Engineering Intelligence Platform | "
    "Evidence → Correlation → Activity → Capacity Leakage → Review"
)

# -------------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------------
with st.sidebar:
    st.header("Reviewer Controls")

    if st.button("🔄 Refresh Dashboard", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

    st.divider()

    st.subheader("Filters")

    service_options = query_df(
        """
        SELECT DISTINCT service_name
        FROM seip_capacity_leakage
        WHERE service_name IS NOT NULL
        ORDER BY service_name
        """
    )["service_name"].tolist()

    leakage_options = query_df(
        """
        SELECT DISTINCT leakage_type
        FROM seip_capacity_leakage
        WHERE leakage_type IS NOT NULL
        ORDER BY leakage_type
        """
    )["leakage_type"].tolist()

    priority_options = query_df(
        """
        SELECT DISTINCT priority
        FROM seip_review_queue
        WHERE priority IS NOT NULL
        ORDER BY priority
        """
    )["priority"].tolist()

    selected_services = st.multiselect(
        "Service",
        service_options,
        default=[],
    )

    selected_leakage = st.multiselect(
        "Leakage Type",
        leakage_options,
        default=[],
    )

    selected_priority = st.multiselect(
        "Priority",
        priority_options,
        default=[],
    )

# -------------------------------------------------------------------
# KPI queries
# -------------------------------------------------------------------
counts = query_df(
    """
    SELECT
        (SELECT COUNT(*) FROM seip_evidence) AS evidence_count,
        (SELECT COUNT(*) FROM seip_correlation_group) AS correlation_count,
        (SELECT COUNT(*) FROM seip_activity) AS activity_count,
        (SELECT COUNT(*) FROM seip_capacity_leakage) AS leakage_count,
        (SELECT COALESCE(SUM(estimated_hours), 0) FROM seip_capacity_leakage
            WHERE status = 'OPEN') AS leakage_hours,
        (SELECT COUNT(*) FROM seip_review_queue
            WHERE status = 'OPEN') AS open_reviews
    """
).iloc[0]

# -------------------------------------------------------------------
# KPI cards
# -------------------------------------------------------------------
st.subheader("Phase 1 Overview")

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric("Evidence", f"{int(counts['evidence_count']):,}")
c2.metric("Correlations", f"{int(counts['correlation_count']):,}")
c3.metric("Activities", f"{int(counts['activity_count']):,}")
c4.metric("Leakage Records", f"{int(counts['leakage_count']):,}")
c5.metric("Open Leakage Hours", f"{float(counts['leakage_hours']):,.1f}")
c6.metric("Open Reviews", f"{int(counts['open_reviews']):,}")

# -------------------------------------------------------------------
# Capacity Leakage
# -------------------------------------------------------------------
st.subheader("Capacity Leakage")

leakage_where = []
leakage_params = []

if selected_services:
    leakage_where.append("service_name = ANY(%s)")
    leakage_params.append(selected_services)

if selected_leakage:
    leakage_where.append("leakage_type = ANY(%s)")
    leakage_params.append(selected_leakage)

where_sql = ""
if leakage_where:
    where_sql = "WHERE " + " AND ".join(leakage_where)

leakage_summary = query_df(
    f"""
    SELECT
        leakage_type,
        COUNT(*) AS leakage_records,
        SUM(activity_count) AS activities,
        ROUND(SUM(estimated_minutes)::numeric / 60, 2) AS estimated_hours,
        ROUND(AVG(confidence)::numeric, 2) AS avg_confidence
    FROM seip_capacity_leakage
    {where_sql}
    GROUP BY leakage_type
    ORDER BY estimated_hours DESC
    """,
    leakage_params,
)

if not leakage_summary.empty:
    left, right = st.columns(2)

    with left:
        st.markdown("**Leakage by Type**")
        chart_df = leakage_summary.set_index("leakage_type")["estimated_hours"]
        st.bar_chart(chart_df)

    with right:
        st.markdown("**Leakage Summary**")
        st.dataframe(
            leakage_summary,
            use_container_width=True,
            hide_index=True,
        )
else:
    st.info("No leakage records match the selected filters.")

# -------------------------------------------------------------------
# Service breakdown
# -------------------------------------------------------------------
st.subheader("Service Breakdown")

service_summary = query_df(
    f"""
    SELECT
        service_name,
        COUNT(*) AS leakage_records,
        SUM(activity_count) AS activities,
        ROUND(SUM(estimated_minutes)::numeric / 60, 2) AS estimated_hours,
        ROUND(AVG(confidence)::numeric, 2) AS avg_confidence
    FROM seip_capacity_leakage
    {where_sql}
    GROUP BY service_name
    ORDER BY estimated_hours DESC
    """,
    leakage_params,
)

if not service_summary.empty:
    st.dataframe(
        service_summary,
        use_container_width=True,
        hide_index=True,
    )

# -------------------------------------------------------------------
# Reviewer Queue
# -------------------------------------------------------------------
st.subheader("Reviewer Queue")

review_where = []
review_params = []

if selected_priority:
    review_where.append("rq.priority = ANY(%s)")
    review_params.append(selected_priority)

if selected_services:
    review_where.append("cl.service_name = ANY(%s)")
    review_params.append(selected_services)

if selected_leakage:
    review_where.append("cl.leakage_type = ANY(%s)")
    review_params.append(selected_leakage)

review_where_sql = ""
if review_where:
    review_where_sql = "WHERE " + " AND ".join(review_where)

review_queue = query_df(
    f"""
    SELECT
        rq.review_id,
        rq.priority,
        rq.status,
        rq.reason,
        rq.confidence,
        cl.service_name,
        cl.pattern_id,
        cl.leakage_type,
        cl.activity_count,
        ROUND(cl.estimated_hours::numeric, 2) AS estimated_hours,
        cl.evidence_count,
        rq.created_at
    FROM seip_review_queue rq
    JOIN seip_capacity_leakage cl
      ON rq.object_type = 'CAPACITY_LEAKAGE'
     AND rq.object_id = cl.leakage_id
    {review_where_sql}
    ORDER BY
        CASE rq.priority
            WHEN 'HIGH' THEN 1
            WHEN 'MEDIUM' THEN 2
            WHEN 'LOW' THEN 3
            ELSE 4
        END,
        cl.estimated_hours DESC,
        rq.review_id
    """,
    review_params,
)

if review_queue.empty:
    st.info("No review items match the selected filters.")
else:
    st.dataframe(
        review_queue,
        use_container_width=True,
        hide_index=True,
    )

# -------------------------------------------------------------------
# Review Detail
# -------------------------------------------------------------------
st.subheader("Review Detail")

if not review_queue.empty:
    review_ids = review_queue["review_id"].astype(int).tolist()

    selected_review_id = st.selectbox(
        "Select Review ID",
        review_ids,
    )

    detail = query_df(
        """
        SELECT
            rq.review_id,
            rq.priority,
            rq.status AS review_status,
            rq.reason,
            rq.confidence AS review_confidence,
            rq.reviewer_comments,
            rq.created_at AS review_created_at,
            cl.leakage_id,
            cl.correlation_id,
            cl.service_name,
            cl.pattern_id,
            cl.leakage_type,
            cl.activity_count,
            cl.estimated_minutes,
            cl.estimated_hours,
            cl.evidence_count,
            cl.confidence AS leakage_confidence,
            cl.explanation,
            cl.status AS leakage_status
        FROM seip_review_queue rq
        JOIN seip_capacity_leakage cl
          ON rq.object_type = 'CAPACITY_LEAKAGE'
         AND rq.object_id = cl.leakage_id
        WHERE rq.review_id = %s
        """,
        [int(selected_review_id)],
    )

    if not detail.empty:
        row = detail.iloc[0]

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Priority", str(row["priority"]))
        d2.metric("Leakage Type", str(row["leakage_type"]))
        d3.metric("Estimated Hours", f"{float(row['estimated_hours']):,.2f}")
        d4.metric("Confidence", f"{float(row['leakage_confidence']):.0f}%")

        st.markdown("**Context**")
        st.write(
            f"**Service:** {row['service_name']}  \n"
            f"**Pattern:** {row['pattern_id']}  \n"
            f"**Correlation ID:** {row['correlation_id']}  \n"
            f"**Activity Count:** {row['activity_count']}  \n"
            f"**Evidence Count:** {row['evidence_count']}"
        )

        st.markdown("**Explanation**")
        st.write(row["explanation"] or "No explanation recorded.")

        # Timeline / activities
        st.markdown("**Activity Timeline**")

        activities = query_df(
            """
            SELECT
                activity_id,
                activity_type,
                start_time,
                end_time,
                duration_minutes,
                actor_id,
                assignment_group,
                evidence_count,
                classification,
                classification_reason,
                classification_confidence
            FROM seip_activity
            WHERE correlation_id = %s
            ORDER BY start_time, activity_id
            """,
            [int(row["correlation_id"])],
        )

        if activities.empty:
            st.info("No activities found for this correlation.")
        else:
            st.dataframe(
                activities,
                use_container_width=True,
                hide_index=True,
            )

        # Evidence
        st.markdown("**Evidence Trail**")

        evidence = query_df(
            """
            SELECT
                e.evidence_id,
                e.source_table,
                e.source_record_id,
                e.evidence_type,
                e.event_time,
                e.title,
                e.description,
                e.assignment_group,
                e.evidence_confidence,
                e.evidence_quality
            FROM seip_evidence e
            JOIN seip_correlation_evidence ce
              ON ce.evidence_id = e.evidence_id
            WHERE ce.correlation_id = %s
            ORDER BY e.event_time, e.evidence_id
            """,
            [int(row["correlation_id"])],
        )

        if evidence.empty:
            st.info("No evidence found for this correlation.")
        else:
            st.dataframe(
                evidence,
                use_container_width=True,
                hide_index=True,
            )

# -------------------------------------------------------------------
# Processing Status
# -------------------------------------------------------------------
st.subheader("Phase 1 Processing Status")

processing = query_df(
    """
    SELECT
        run_id,
        run_type,
        started_at,
        completed_at,
        status,
        records_read,
        records_created,
        records_updated,
        records_rejected,
        error_count
    FROM seip_processing_runs
    WHERE run_type <> 'PHASE1_VALIDATION'
    ORDER BY run_id
    """
)

st.dataframe(
    processing,
    use_container_width=True,
    hide_index=True,
)

st.caption(
    f"Last dashboard load: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
)
