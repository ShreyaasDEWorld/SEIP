CREATE DATABASE seip_itsm;

SELECT table_schema, table_name 
FROM information_schema.tables 
WHERE table_type = 'BASE TABLE' and table_schema='public'
ORDER BY table_schema, table_name;

SELECT COUNT(*) FROM incidents;

SELECT COUNT(*) FROM alerts;

SELECT COUNT(*) FROM resolver_history;

SELECT COUNT(*) FROM changes;

SELECT COUNT(*) FROM change_tasks;

SELECT COUNT(*) FROM approval_history;

SELECT COUNT(*) FROM problem_records;

SELECT COUNT(*) FROM runbooks;