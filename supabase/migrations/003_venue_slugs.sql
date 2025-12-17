-- Add slug field to venues for pretty URLs
-- Migration: 003_venue_slugs.sql

-- Add slug column
ALTER TABLE venues ADD COLUMN IF NOT EXISTS slug TEXT;

-- Create unique index on slug
CREATE UNIQUE INDEX IF NOT EXISTS idx_venues_slug ON venues(slug) WHERE slug IS NOT NULL;

-- Function to generate slug from name
CREATE OR REPLACE FUNCTION generate_slug(name TEXT)
RETURNS TEXT AS $$
DECLARE
    base_slug TEXT;
    final_slug TEXT;
    counter INTEGER := 0;
BEGIN
    -- Convert to lowercase, replace spaces and special chars with hyphens
    base_slug := lower(regexp_replace(name, '[^a-zA-Z0-9]+', '-', 'g'));
    -- Remove leading/trailing hyphens
    base_slug := trim(both '-' from base_slug);

    final_slug := base_slug;

    -- Check for uniqueness and append number if needed
    WHILE EXISTS (SELECT 1 FROM venues WHERE slug = final_slug) LOOP
        counter := counter + 1;
        final_slug := base_slug || '-' || counter;
    END LOOP;

    RETURN final_slug;
END;
$$ LANGUAGE plpgsql;

-- Update existing venues with slugs
UPDATE venues SET slug = generate_slug(name) WHERE slug IS NULL;

-- Make slug NOT NULL after populating existing records
ALTER TABLE venues ALTER COLUMN slug SET NOT NULL;

-- Trigger to auto-generate slug on insert
CREATE OR REPLACE FUNCTION set_venue_slug()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.slug IS NULL OR NEW.slug = '' THEN
        NEW.slug := generate_slug(NEW.name);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS venue_slug_trigger ON venues;
CREATE TRIGGER venue_slug_trigger
    BEFORE INSERT ON venues
    FOR EACH ROW
    EXECUTE FUNCTION set_venue_slug();

COMMENT ON COLUMN venues.slug IS 'URL-friendly slug generated from venue name';
