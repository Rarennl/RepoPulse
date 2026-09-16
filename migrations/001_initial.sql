-- Schema v1. Apply only to an empty database. Runtime migrate() uses this equivalent metadata.

BEGIN;

CREATE TABLE schema_version (version INTEGER PRIMARY KEY);


CREATE TABLE accounts (
	id VARCHAR(128) NOT NULL, 
	display_name VARCHAR(256) NOT NULL, 
	token TEXT, 
	PRIMARY KEY (id)
)

;


CREATE TABLE analyses (
	id VARCHAR(36) NOT NULL, 
	repo_id VARCHAR(36) NOT NULL, 
	created_at FLOAT NOT NULL, 
	score FLOAT, 
	coverage FLOAT NOT NULL, 
	result JSON NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_analyses_repo_id ON analyses (repo_id);


CREATE TABLE jobs (
	id VARCHAR(36) NOT NULL, 
	repo_id VARCHAR(36) NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	available_at FLOAT NOT NULL, 
	lease_until FLOAT NOT NULL, 
	lease_token VARCHAR(36), 
	created_at FLOAT NOT NULL, 
	finished_at FLOAT, 
	error VARCHAR(256), 
	PRIMARY KEY (id)
)

;

CREATE INDEX ix_jobs_state ON jobs (state);

CREATE INDEX ix_jobs_repo_id ON jobs (repo_id);


CREATE TABLE repositories (
	id VARCHAR(36) NOT NULL, 
	slug VARCHAR(256) NOT NULL, 
	scope VARCHAR(128) NOT NULL, 
	metadata_json JSON NOT NULL, 
	latest_id VARCHAR(36), 
	last_attempt FLOAT NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE UNIQUE INDEX uq_repo_scope ON repositories (slug, scope);

INSERT INTO schema_version VALUES (1);

COMMIT;