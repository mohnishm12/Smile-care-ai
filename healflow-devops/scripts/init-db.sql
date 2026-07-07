-- =============================================================================
-- HealFlow AI — Database Initialization Script
-- Run automatically by PostgreSQL on first container startup
-- =============================================================================

-- Enable pgvector extension for AI embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable uuid-ossp for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgcrypto for encryption functions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Create schema for the application
CREATE SCHEMA IF NOT EXISTS healflow;

-- Set search path
ALTER DATABASE healflow SET search_path TO healflow, public;

-- Create roles
CREATE ROLE healflow_app WITH LOGIN PASSWORD 'change-me-in-production';
CREATE ROLE healflow_readonly WITH LOGIN PASSWORD 'change-me-in-production';

-- Grant permissions
GRANT USAGE ON SCHEMA healflow TO healflow_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA healflow TO healflow_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA healflow TO healflow_app;

GRANT USAGE ON SCHEMA healflow TO healflow_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA healflow TO healflow_readonly;