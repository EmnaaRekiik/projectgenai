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

COMMIT;

