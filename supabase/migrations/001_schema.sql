-- Venue Seat Views Database Schema
-- Run this in Supabase SQL Editor to set up the database

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Venues table
CREATE TABLE IF NOT EXISTS venues (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    location TEXT,
    has_seatmap BOOLEAN DEFAULT FALSE,
    has_model BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sections table
CREATE TABLE IF NOT EXISTS sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    section_id TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'Standard',
    angle FLOAT NOT NULL DEFAULT 0,
    inner_radius FLOAT NOT NULL DEFAULT 20,
    rows INTEGER NOT NULL DEFAULT 10,
    row_depth FLOAT NOT NULL DEFAULT 0.8,
    row_rise FLOAT NOT NULL DEFAULT 0.3,
    base_height FLOAT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(venue_id, section_id)
);

-- Images table
CREATE TABLE IF NOT EXISTS images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    seat_id TEXT NOT NULL,
    section TEXT NOT NULL,
    row TEXT NOT NULL,
    seat INTEGER NOT NULL,
    tier TEXT NOT NULL,
    depth_map_url TEXT,
    final_image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(venue_id, seat_id)
);

-- Pipeline runs table (for tracking Temporal workflows)
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    workflow_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    stage TEXT,
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    message TEXT,
    seats_generated INTEGER DEFAULT 0,
    depth_maps_rendered INTEGER DEFAULT 0,
    images_generated INTEGER DEFAULT 0,
    actual_cost FLOAT DEFAULT 0,
    failed_items JSONB DEFAULT '[]',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_sections_venue_id ON sections(venue_id);
CREATE INDEX IF NOT EXISTS idx_images_venue_id ON images(venue_id);
CREATE INDEX IF NOT EXISTS idx_images_section ON images(venue_id, section);
CREATE INDEX IF NOT EXISTS idx_images_tier ON images(venue_id, tier);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_venue_id ON pipeline_runs(venue_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_workflow_id ON pipeline_runs(workflow_id);

-- Updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers
DROP TRIGGER IF EXISTS update_venues_updated_at ON venues;
CREATE TRIGGER update_venues_updated_at
    BEFORE UPDATE ON venues
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_images_updated_at ON images;
CREATE TRIGGER update_images_updated_at
    BEFORE UPDATE ON images
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security (optional - enable if using Supabase Auth)
-- ALTER TABLE venues ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE sections ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE images ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;

-- Grant access to authenticated users (if using RLS)
-- CREATE POLICY "Users can view all venues" ON venues FOR SELECT USING (true);
-- CREATE POLICY "Users can insert venues" ON venues FOR INSERT WITH CHECK (true);
-- CREATE POLICY "Users can update venues" ON venues FOR UPDATE USING (true);
-- CREATE POLICY "Users can delete venues" ON venues FOR DELETE USING (true);

COMMENT ON TABLE venues IS 'Stores venue information';
COMMENT ON TABLE sections IS 'Stores section configurations for each venue';
COMMENT ON TABLE images IS 'Stores generated seat view images';
COMMENT ON TABLE pipeline_runs IS 'Tracks pipeline/workflow execution status';
