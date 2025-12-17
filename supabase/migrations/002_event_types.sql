-- Migration: Add Event Types and Seatmap Extraction Support
-- Run this in Supabase SQL Editor after the initial schema

-- =====================================================
-- EVENT TYPES TABLE
-- Stores different event configurations per venue (hockey, basketball, concert)
-- =====================================================
CREATE TABLE IF NOT EXISTS event_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                           -- 'hockey', 'basketball', 'concert'
    display_name TEXT NOT NULL,                   -- 'Hockey', 'Basketball', 'Concert'
    seatmap_url TEXT,                             -- URL to seatmap image in Supabase storage
    reference_image_url TEXT,                     -- URL to reference photo for IP-Adapter style transfer
    surface_type TEXT NOT NULL DEFAULT 'rink',    -- 'rink', 'court', 'stage', 'field'
    surface_config JSONB DEFAULT '{}',            -- {length: 60, width: 26, boards: true, ...}
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(venue_id, name)
);

CREATE INDEX IF NOT EXISTS idx_event_types_venue_id ON event_types(venue_id);

-- =====================================================
-- SEATMAP EXTRACTIONS TABLE
-- Stores AI extraction results for review before finalizing
-- =====================================================
CREATE TABLE IF NOT EXISTS seatmap_extractions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    venue_id UUID NOT NULL REFERENCES venues(id) ON DELETE CASCADE,
    event_type_id UUID REFERENCES event_types(id) ON DELETE CASCADE,
    seatmap_url TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'replicate',   -- 'replicate' or 'openai'
    status TEXT NOT NULL DEFAULT 'pending',       -- 'pending', 'processing', 'completed', 'failed'
    raw_extraction JSONB,                         -- Raw AI model output
    extracted_sections JSONB,                     -- Processed section definitions
    confidence_scores JSONB,                      -- Per-section confidence {section_id: 0.85, ...}
    user_adjustments JSONB,                       -- User modifications before finalization
    finalized_at TIMESTAMP WITH TIME ZONE,        -- When sections were committed
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seatmap_extractions_venue_id ON seatmap_extractions(venue_id);
CREATE INDEX IF NOT EXISTS idx_seatmap_extractions_event_type_id ON seatmap_extractions(event_type_id);
CREATE INDEX IF NOT EXISTS idx_seatmap_extractions_status ON seatmap_extractions(status);

-- =====================================================
-- ADD EVENT_TYPE_ID TO SECTIONS TABLE
-- Links sections to specific event types
-- =====================================================
ALTER TABLE sections ADD COLUMN IF NOT EXISTS event_type_id UUID REFERENCES event_types(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_sections_event_type_id ON sections(event_type_id);

-- =====================================================
-- ADD EVENT_TYPE_ID TO PIPELINE_RUNS TABLE
-- Track which event type a pipeline run is for
-- =====================================================
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS event_type_id UUID REFERENCES event_types(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_event_type_id ON pipeline_runs(event_type_id);

-- =====================================================
-- ADD EVENT_TYPE_ID TO IMAGES TABLE
-- Link generated images to their event type
-- =====================================================
ALTER TABLE images ADD COLUMN IF NOT EXISTS event_type_id UUID REFERENCES event_types(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_images_event_type_id ON images(event_type_id);

-- =====================================================
-- UPDATED_AT TRIGGER FOR EVENT_TYPES
-- =====================================================
DROP TRIGGER IF EXISTS update_event_types_updated_at ON event_types;
CREATE TRIGGER update_event_types_updated_at
    BEFORE UPDATE ON event_types
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- UPDATE VENUES TABLE
-- Add event_types_count computed column (optional view)
-- =====================================================
CREATE OR REPLACE VIEW venues_with_counts AS
SELECT
    v.*,
    (SELECT COUNT(*) FROM sections s WHERE s.venue_id = v.id) as sections_count,
    (SELECT COUNT(*) FROM images i WHERE i.venue_id = v.id) as images_count,
    (SELECT COUNT(*) FROM event_types e WHERE e.venue_id = v.id) as event_types_count
FROM venues v;

-- =====================================================
-- COMMENTS
-- =====================================================
COMMENT ON TABLE event_types IS 'Stores event type configurations (hockey, basketball, concert) per venue';
COMMENT ON TABLE seatmap_extractions IS 'Stores AI-extracted section data for review before finalizing';
COMMENT ON COLUMN event_types.seatmap_url IS 'URL to the seatmap PNG used for section extraction';
COMMENT ON COLUMN event_types.reference_image_url IS 'URL to reference photo for IP-Adapter style transfer';
COMMENT ON COLUMN event_types.surface_type IS 'Type of playing surface: rink, court, stage, field';
COMMENT ON COLUMN event_types.surface_config IS 'JSON config for surface dimensions and features';
COMMENT ON COLUMN seatmap_extractions.provider IS 'AI provider used: replicate or openai';
COMMENT ON COLUMN seatmap_extractions.confidence_scores IS 'Per-section confidence from AI extraction';
