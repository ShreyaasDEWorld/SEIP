# SEIP — Synthetic ITSM Dataset Generator

A ServiceNow-inspired synthetic ITSM data generator for the SEIP Executable Multiagent System.

## What it generates

- Incidents
- Monitoring alerts
- Change records
- Change tasks
- Approval workflow history
- Resolver history
- Problem records / known errors
- Runbooks
- CMDB configuration items
- Users / resolver teams

The data is intentionally relational. A recurring operational pattern can therefore appear across:

`Alert -> Incident -> Resolver History -> Problem -> Runbook -> Change -> Change Tasks -> Approvals`

This makes the dataset useful for recurrence detection, incident similarity, change recommendation, runbook recommendation and agentic decision support.

## Technology patterns

The initial taxonomy includes:

- PostgreSQL / Database
- Network
- Unix
- Red Hat Linux
- ServiceNow integrations

The generator can be extended with Oracle, Sybase ASE, MSSQL, Kubernetes, Azure, AWS, middleware, storage, backup, security, etc.

## 1. Create database

From psql:

```sql
CREATE DATABASE seip_itsm;
```

Or use pgAdmin.

## 2. Configure environment

Copy `.env.example` to `.env` and set your PostgreSQL connection values.

PowerShell example:

```powershell
$env:PGHOST="localhost"
$env:PGPORT="5432"
$env:PGDATABASE="seip_itsm"
$env:PGUSER="postgres"
$env:PGPASSWORD="your_password"
```

## 3. Install

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## 4. Generate data

Generate 5,000 historical incidents:

```powershell
python generator.py --incidents 5000
```

Generate 200 new incidents for a daily run:

```powershell
python generator.py --incidents 200
```

Because the generator uses the current timestamp and randomized operational events, each execution produces a new batch.

## Recommended SEIP architecture

```text
                 ┌──────────────────────┐
                 │ Synthetic ITSM Data  │
                 └──────────┬───────────┘
                            │
      ┌─────────────────────┼──────────────────────┐
      ▼                     ▼                      ▼
  Incident Agent       Pattern Agent         Change Agent
      │                     │                      │
      └──────────────┬──────┴──────────────┬───────┘
                     ▼                     ▼
               Evidence/RAG Agent     Runbook Agent
                     │                     │
                     └──────────┬──────────┘
                                ▼
                     Recommendation Agent
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
              Auto suggestion          Human approval
```

## High-value AI fields

The most important fields for recurrence analysis are:

- `normalized_pattern_id`
- `symptom_signature`
- `short_description`
- `description`
- `ci_id`
- `service`
- `category`
- `subcategory`
- `assignment_group`
- `problem_id`
- `runbook_id`
- resolver actions
- alert metrics
- change implementation plan
- change task results
- approval history

Do not remove `normalized_pattern_id`. It is a synthetic ground-truth label that can be hidden from an ML/LLM agent during evaluation and used afterward to measure whether the agent discovered the correct recurring pattern.

## Example future SEIP questions

1. "Have we seen this incident before?"
2. "Show similar incidents from the last 90 days."
3. "What resolver actions previously fixed this?"
4. "Is there a known problem associated with this symptom?"
5. "Which runbook worked most often?"
6. "Was a change required for previous occurrences?"
7. "What change tasks were executed?"
8. "Which approvals were required?"
9. "Should this incident be linked to an existing problem?"
10. "Should SEIP recommend creating a new problem/change?"
