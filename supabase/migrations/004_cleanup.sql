-- Cleanup migration
-- Drop unused pipeline_runs table (Temporal Cloud tracks workflow state natively)

-- Drop indexes first
DROP INDEX IF EXISTS idx_pipeline_runs_venue_id;
DROP INDEX IF EXISTS idx_pipeline_runs_workflow_id;

-- Drop the table
DROP TABLE IF EXISTS pipeline_runs;
