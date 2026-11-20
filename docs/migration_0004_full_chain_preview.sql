BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_catalogue

CREATE TABLE institutions (
    id UUID NOT NULL, 
    code VARCHAR(20) NOT NULL, 
    name VARCHAR(160) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (code)
);

CREATE TABLE programs (
    id UUID NOT NULL, 
    institution_id UUID NOT NULL, 
    code VARCHAR(50) NOT NULL, 
    title VARCHAR(180) NOT NULL, 
    level VARCHAR(20) NOT NULL, 
    duration_years INTEGER, 
    description TEXT, 
    official_source_url VARCHAR(500), 
    verified_at TIMESTAMP WITH TIME ZONE, 
    status VARCHAR(12) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_program_institution_code UNIQUE (institution_id, code), 
    CONSTRAINT ck_program_duration CHECK (duration_years BETWEEN 1 AND 10), 
    CONSTRAINT ck_program_level CHECK (level IN ('LICENCE', 'PREPARATORY', 'ENGINEERING', 'OTHER')), 
    CONSTRAINT ck_program_status CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')), 
    CONSTRAINT ck_program_published_has_evidence CHECK (status <> 'PUBLISHED' OR (official_source_url IS NOT NULL AND verified_at IS NOT NULL)), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_program_institution_level ON programs (institution_id, level);

CREATE INDEX ix_program_status ON programs (status);

INSERT INTO alembic_version (version_num) VALUES ('0001_catalogue') RETURNING alembic_version.version_num;

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

-- Running upgrade 0002_visitor_memory -> 0003_chat_lease

ALTER TABLE visitor_sessions ADD COLUMN chat_request_id UUID;

ALTER TABLE visitor_sessions ADD COLUMN chat_lease_until TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0003_chat_lease' WHERE alembic_version.version_num = '0002_visitor_memory';

-- Running upgrade 0003_chat_lease -> 0004_staff_auth

CREATE TABLE staff_users (
    id UUID NOT NULL, 
    email VARCHAR(254) NOT NULL, 
    display_name VARCHAR(120) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    role VARCHAR(32) NOT NULL, 
    institution_id UUID, 
    is_active BOOLEAN NOT NULL, 
    failed_login_count INTEGER NOT NULL, 
    locked_until TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_staff_role CHECK (role IN ('PLATFORM_ADMIN','ACADEMIC_IIT','ACADEMIC_ISB','INTERVIEW_MANAGER','DIRECTION')), 
    CONSTRAINT ck_staff_academic_institution CHECK (role NOT IN ('ACADEMIC_IIT','ACADEMIC_ISB') OR institution_id IS NOT NULL), 
    CONSTRAINT ck_staff_login_count CHECK (failed_login_count >= 0), 
    UNIQUE (email), 
    FOREIGN KEY(institution_id) REFERENCES institutions (id) ON DELETE RESTRICT
);

CREATE TABLE staff_sessions (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES staff_users (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_staff_sessions_user_id ON staff_sessions (user_id);

CREATE INDEX ix_staff_sessions_expires_at ON staff_sessions (expires_at);

UPDATE alembic_version SET version_num='0004_staff_auth' WHERE alembic_version.version_num = '0003_chat_lease';

COMMIT;

