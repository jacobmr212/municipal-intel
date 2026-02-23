-- Migration: Create resource_downloads table for tracking playbook downloads
-- Date: 2026-02-22

CREATE TABLE IF NOT EXISTS resource_downloads (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    name TEXT,
    municipality TEXT,
    resource_name TEXT NOT NULL,
    downloaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_agent TEXT,
    ip_address TEXT
);

-- Index for email lookups
CREATE INDEX IF NOT EXISTS idx_resource_downloads_email ON resource_downloads(email);

-- Index for resource name lookups
CREATE INDEX IF NOT EXISTS idx_resource_downloads_resource_name ON resource_downloads(resource_name);

-- Index for download date (for analytics)
CREATE INDEX IF NOT EXISTS idx_resource_downloads_downloaded_at ON resource_downloads(downloaded_at DESC);
