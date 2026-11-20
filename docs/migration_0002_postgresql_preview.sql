BEGIN;

-- Running upgrade 0001_catalogue -> 0002_visitor_memory

CREATE TABLE visitor_sessions (
    id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_activity_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    next_message_sequence INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_visitor_next_sequence CHECK (next_message_sequence >= 1), 
    UNIQUE (token_hash)
);

CREATE INDEX ix_visitor_sessions_expires_at ON visitor_sessions (expires_at);

CREATE TABLE conversation_messages (
    id UUID NOT NULL, 
    session_id UUID NOT NULL, 
    sequence INTEGER NOT NULL, 
    role VARCHAR(12) NOT NULL, 
    content TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_conversation_session_sequence UNIQUE (session_id, sequence), 
    CONSTRAINT ck_conversation_message_role CHECK (role IN ('user', 'assistant')), 
    CONSTRAINT ck_conversation_sequence_positive CHECK (sequence >= 1), 
    FOREIGN KEY(session_id) REFERENCES visitor_sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_conversation_messages_session_id_sequence ON conversation_messages (session_id, sequence);

UPDATE alembic_version SET version_num='0002_visitor_memory' WHERE alembic_version.version_num = '0001_catalogue';

COMMIT;

