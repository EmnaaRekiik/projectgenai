BEGIN;

-- Running upgrade 0002_visitor_memory -> 0003_chat_lease

ALTER TABLE visitor_sessions ADD COLUMN chat_request_id UUID;

ALTER TABLE visitor_sessions ADD COLUMN chat_lease_until TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0003_chat_lease' WHERE alembic_version.version_num = '0002_visitor_memory';

COMMIT;

