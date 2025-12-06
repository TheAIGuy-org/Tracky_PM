-- ==========================================
-- MIGRATION 002: Critical Fixes for Production
-- ==========================================
-- This migration addresses all architect-identified issues:
-- 1. Remove CASCADE DELETE (data loss prevention)
-- 2. Add soft-delete triggers
-- 3. Upgrade to UUIDv7 (performance at scale)
-- 4. Add compound/partial indexes
-- 5. Create audit_logs table (compliance)
-- 6. Create baseline_versions table (scope tracking)
-- 7. Create resource_utilization view
-- ==========================================

-- ==========================================
-- STEP 1: Remove CASCADE DELETE and Add Soft-Delete Triggers
-- ==========================================

-- 1A. First, drop existing foreign key constraints with CASCADE
ALTER TABLE work_items DROP CONSTRAINT IF EXISTS work_items_phase_id_fkey;
ALTER TABLE phases DROP CONSTRAINT IF EXISTS phases_project_id_fkey;
ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_program_id_fkey;
ALTER TABLE dependencies DROP CONSTRAINT IF EXISTS dependencies_successor_item_id_fkey;
ALTER TABLE dependencies DROP CONSTRAINT IF EXISTS dependencies_predecessor_item_id_fkey;

-- 1B. Re-add foreign keys WITHOUT CASCADE (RESTRICT is default, safer)
ALTER TABLE work_items 
  ADD CONSTRAINT work_items_phase_id_fkey 
  FOREIGN KEY (phase_id) REFERENCES phases(id) ON DELETE RESTRICT;

ALTER TABLE phases 
  ADD CONSTRAINT phases_project_id_fkey 
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT;

ALTER TABLE projects 
  ADD CONSTRAINT projects_program_id_fkey 
  FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE RESTRICT;

-- Dependencies can still cascade (if work item deleted, dependency meaningless)
ALTER TABLE dependencies 
  ADD CONSTRAINT dependencies_successor_item_id_fkey 
  FOREIGN KEY (successor_item_id) REFERENCES work_items(id) ON DELETE CASCADE;

ALTER TABLE dependencies 
  ADD CONSTRAINT dependencies_predecessor_item_id_fkey 
  FOREIGN KEY (predecessor_item_id) REFERENCES work_items(id) ON DELETE CASCADE;

-- 1C. Add status column to phases and projects for soft delete
ALTER TABLE phases ADD COLUMN IF NOT EXISTS status text DEFAULT 'Active';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS status text DEFAULT 'Active';

-- 1D. Create soft-delete cascade trigger for phases
CREATE OR REPLACE FUNCTION cascade_soft_delete_phase()
RETURNS TRIGGER AS $$
BEGIN
  -- When a phase is cancelled, cascade to all its work items
  IF NEW.status = 'Cancelled' AND (OLD.status IS NULL OR OLD.status != 'Cancelled') THEN
    UPDATE work_items 
    SET status = 'Cancelled', 
        updated_at = now()
    WHERE phase_id = NEW.id 
    AND status != 'Cancelled';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS phase_soft_delete_trigger ON phases;
CREATE TRIGGER phase_soft_delete_trigger
AFTER UPDATE OF status ON phases
FOR EACH ROW
EXECUTE FUNCTION cascade_soft_delete_phase();

-- 1E. Create soft-delete cascade trigger for projects
CREATE OR REPLACE FUNCTION cascade_soft_delete_project()
RETURNS TRIGGER AS $$
BEGIN
  -- When a project is cancelled, cascade to all its phases
  IF NEW.status = 'Cancelled' AND (OLD.status IS NULL OR OLD.status != 'Cancelled') THEN
    UPDATE phases 
    SET status = 'Cancelled'
    WHERE project_id = NEW.id 
    AND status != 'Cancelled';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS project_soft_delete_trigger ON projects;
CREATE TRIGGER project_soft_delete_trigger
AFTER UPDATE OF status ON projects
FOR EACH ROW
EXECUTE FUNCTION cascade_soft_delete_project();

-- 1F. Create soft-delete cascade trigger for programs
CREATE OR REPLACE FUNCTION cascade_soft_delete_program()
RETURNS TRIGGER AS $$
BEGIN
  -- When a program is cancelled, cascade to all its projects
  IF NEW.status::text = 'Cancelled' AND (OLD.status IS NULL OR OLD.status::text != 'Cancelled') THEN
    UPDATE projects 
    SET status = 'Cancelled'
    WHERE program_id = NEW.id 
    AND status != 'Cancelled';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS program_soft_delete_trigger ON programs;
CREATE TRIGGER program_soft_delete_trigger
AFTER UPDATE OF status ON programs
FOR EACH ROW
EXECUTE FUNCTION cascade_soft_delete_program();


-- ==========================================
-- STEP 2: Upgrade to UUIDv7 for Better Performance
-- ==========================================

-- 2A. Create UUIDv7 generation function (Postgres 13+ compatible)
-- UUIDv7 embeds timestamp in first 48 bits for sortable, index-friendly UUIDs
CREATE OR REPLACE FUNCTION uuid_generate_v7()
RETURNS uuid AS $$
DECLARE
  unix_ts_ms bytea;
  uuid_bytes bytea;
BEGIN
  -- Get current timestamp in milliseconds
  unix_ts_ms = substring(int8send(floor(extract(epoch from clock_timestamp()) * 1000)::bigint) from 3);
  
  -- Generate random bytes for the rest
  uuid_bytes = unix_ts_ms || gen_random_bytes(10);
  
  -- Set version (7) and variant (RFC 4122)
  uuid_bytes = set_byte(uuid_bytes, 6, (get_byte(uuid_bytes, 6) & 15) | 112);  -- version 7
  uuid_bytes = set_byte(uuid_bytes, 8, (get_byte(uuid_bytes, 8) & 63) | 128);  -- variant
  
  RETURN encode(uuid_bytes, 'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;

-- 2B. Update default UUID generation for new tables (existing data keeps UUIDv4)
-- Note: We don't change existing IDs, just new ones will use v7

ALTER TABLE resources ALTER COLUMN id SET DEFAULT uuid_generate_v7();
ALTER TABLE programs ALTER COLUMN id SET DEFAULT uuid_generate_v7();
ALTER TABLE projects ALTER COLUMN id SET DEFAULT uuid_generate_v7();
ALTER TABLE phases ALTER COLUMN id SET DEFAULT uuid_generate_v7();
ALTER TABLE work_items ALTER COLUMN id SET DEFAULT uuid_generate_v7();
ALTER TABLE dependencies ALTER COLUMN id SET DEFAULT uuid_generate_v7();
ALTER TABLE magic_tokens ALTER COLUMN token_hash SET DEFAULT uuid_generate_v7()::text;


-- ==========================================
-- STEP 3: Add Compound and Partial Indexes for Performance
-- ==========================================

-- 3A. Compound index for Smart Merge lookups (program + external_id)
-- This is the most frequent query during import
DROP INDEX IF EXISTS idx_work_items_phase_external;
CREATE INDEX idx_work_items_phase_external 
ON work_items(phase_id, external_id);

-- 3B. Compound index for dependency lookups
DROP INDEX IF EXISTS idx_dependencies_successor_predecessor;
CREATE INDEX idx_dependencies_successor_predecessor 
ON dependencies(successor_item_id, predecessor_item_id);

-- 3C. Partial index for active items only (dashboards filter by status)
-- This dramatically speeds up dashboard queries
DROP INDEX IF EXISTS idx_work_items_active_status;
CREATE INDEX idx_work_items_active_status 
ON work_items(status) 
WHERE status NOT IN ('Cancelled', 'Completed');

-- 3D. Index for resource utilization queries
DROP INDEX IF EXISTS idx_work_items_resource_active;
CREATE INDEX idx_work_items_resource_active 
ON work_items(resource_id, status) 
WHERE status NOT IN ('Cancelled', 'Completed');

-- 3E. Index for timeline queries (sorted by dates)
DROP INDEX IF EXISTS idx_work_items_current_dates;
CREATE INDEX idx_work_items_current_dates 
ON work_items(current_start, current_end);

-- 3F. Index for audit log queries
DROP INDEX IF EXISTS idx_work_items_updated_at;
CREATE INDEX idx_work_items_updated_at 
ON work_items(updated_at DESC);


-- ==========================================
-- STEP 4: Create Audit Trail Tables (Compliance: SOX, GDPR, ISO)
-- ==========================================

-- 4A. Main audit log table
CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  
  -- What entity was changed
  entity_type text NOT NULL,          -- 'work_item', 'phase', 'project', 'program'
  entity_id uuid NOT NULL,
  
  -- What changed
  action text NOT NULL,               -- 'created', 'updated', 'cancelled', 'restored'
  field_changed text,                 -- 'planned_end', 'status', etc.
  old_value text,
  new_value text,
  
  -- Context
  change_source text NOT NULL,        -- 'excel_import', 'api_update', 'manual', 'system'
  import_batch_id uuid,               -- Links all changes in one import
  
  -- Who/When
  changed_by text,                    -- email or 'system:excel_import'
  changed_at timestamptz DEFAULT now(),
  
  -- Additional context
  reason text,                        -- 'Progressive elaboration', 'Approved CR-123'
  metadata jsonb                      -- Additional context as JSON
);

-- 4B. Indexes for audit queries
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id, changed_at DESC);
CREATE INDEX idx_audit_logs_batch ON audit_logs(import_batch_id) WHERE import_batch_id IS NOT NULL;
CREATE INDEX idx_audit_logs_changed_at ON audit_logs(changed_at DESC);

-- 4C. Import batches table (tracks each import operation)
CREATE TABLE IF NOT EXISTS import_batches (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  program_id uuid REFERENCES programs(id),
  
  -- Import metadata
  file_name text,
  file_hash text,                     -- SHA256 of uploaded file
  
  -- Results
  status text NOT NULL DEFAULT 'pending',  -- 'pending', 'success', 'partial', 'failed', 'rolled_back'
  
  tasks_created int DEFAULT 0,
  tasks_updated int DEFAULT 0,
  tasks_preserved int DEFAULT 0,
  tasks_cancelled int DEFAULT 0,
  tasks_flagged int DEFAULT 0,        -- Items flagged for review
  
  errors jsonb,                       -- Array of error details
  warnings jsonb,                     -- Array of warning details
  
  -- Who/When
  imported_by text,
  started_at timestamptz DEFAULT now(),
  completed_at timestamptz,
  
  -- Baseline version created by this import
  baseline_version_id uuid
);

CREATE INDEX idx_import_batches_program ON import_batches(program_id, started_at DESC);


-- ==========================================
-- STEP 5: Baseline Versioning (Scope Tracking)
-- ==========================================

-- 5A. Baseline versions table
CREATE TABLE IF NOT EXISTS baseline_versions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v7(),
  program_id uuid REFERENCES programs(id) NOT NULL,
  version_number int NOT NULL,
  
  -- Snapshot of key metrics
  total_tasks int NOT NULL,
  total_planned_effort_hours int,
  planned_start_date date NOT NULL,
  planned_end_date date NOT NULL,
  total_planned_days int NOT NULL,
  
  -- Cost snapshot
  total_budget numeric(15, 2),
  
  -- Metadata
  created_at timestamptz DEFAULT now(),
  created_by text,
  reason_for_change text,             -- 'Initial baseline', 'Progressive elaboration', 'CR-123 approved'
  import_batch_id uuid REFERENCES import_batches(id),
  
  -- Task-level snapshot (JSON for flexibility)
  task_snapshot jsonb,                -- Array of {external_id, planned_start, planned_end, effort}
  
  UNIQUE(program_id, version_number)
);

CREATE INDEX idx_baseline_versions_program ON baseline_versions(program_id, version_number DESC);

-- 5B. Function to get next baseline version number
CREATE OR REPLACE FUNCTION get_next_baseline_version(p_program_id uuid)
RETURNS int AS $$
DECLARE
  max_version int;
BEGIN
  SELECT COALESCE(MAX(version_number), 0) INTO max_version
  FROM baseline_versions
  WHERE program_id = p_program_id;
  
  RETURN max_version + 1;
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 6: Resource Utilization View
-- ==========================================

-- 6A. Create materialized view for resource utilization
CREATE OR REPLACE VIEW resource_utilization AS
SELECT 
  r.id,
  r.external_id,
  r.name,
  r.email,
  r.role,
  r.max_utilization,
  COALESCE(SUM(wi.allocation_percent) FILTER (WHERE wi.status NOT IN ('Cancelled', 'Completed')), 0) as total_allocated_percent,
  r.max_utilization - COALESCE(SUM(wi.allocation_percent) FILTER (WHERE wi.status NOT IN ('Cancelled', 'Completed')), 0) as available_percent,
  COUNT(wi.id) FILTER (WHERE wi.status NOT IN ('Cancelled', 'Completed')) as active_task_count,
  CASE 
    WHEN COALESCE(SUM(wi.allocation_percent) FILTER (WHERE wi.status NOT IN ('Cancelled', 'Completed')), 0) > r.max_utilization THEN 'Over-Allocated'
    WHEN COALESCE(SUM(wi.allocation_percent) FILTER (WHERE wi.status NOT IN ('Cancelled', 'Completed')), 0) > r.max_utilization * 0.8 THEN 'At-Risk'
    ELSE 'Available'
  END as utilization_status
FROM resources r
LEFT JOIN work_items wi ON r.id = wi.resource_id
GROUP BY r.id, r.external_id, r.name, r.email, r.role, r.max_utilization;

-- 6B. Function to check resource over-allocation
CREATE OR REPLACE FUNCTION check_resource_overallocation(p_resource_ids uuid[])
RETURNS TABLE (
  resource_id uuid,
  resource_name text,
  total_allocation int,
  max_utilization int,
  over_by int
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    ru.id,
    ru.name,
    ru.total_allocated_percent::int,
    ru.max_utilization,
    (ru.total_allocated_percent - ru.max_utilization)::int as over_by
  FROM resource_utilization ru
  WHERE ru.id = ANY(p_resource_ids)
  AND ru.total_allocated_percent > ru.max_utilization;
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 7: Add Review Flag Columns for Soft Delete Logic
-- ==========================================

-- Add columns to work_items for flagging items that need PM review
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS flag_for_review boolean DEFAULT false;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS review_message text;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS cancellation_reason text;

-- Index for flagged items
DROP INDEX IF EXISTS idx_work_items_flagged;
CREATE INDEX idx_work_items_flagged 
ON work_items(flag_for_review) 
WHERE flag_for_review = true;


-- ==========================================
-- STEP 8: Critical Path and Recalculation Support
-- ==========================================

-- Add is_critical_path column to work_items
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS is_critical_path boolean DEFAULT false;

-- Function for forward pass calculation (Critical Path Method)
CREATE OR REPLACE FUNCTION calculate_critical_path(p_program_id uuid)
RETURNS TABLE (
  work_item_id uuid,
  external_id text,
  early_start date,
  early_finish date,
  late_start date,
  late_finish date,
  total_float int,
  is_critical boolean
) AS $$
BEGIN
  RETURN QUERY
  WITH RECURSIVE 
  -- Get all work items for this program
  program_work_items AS (
    SELECT 
      wi.id AS wi_id, 
      wi.external_id AS wi_external_id, 
      wi.current_start AS wi_current_start, 
      wi.current_end AS wi_current_end, 
      wi.phase_id AS wi_phase_id,
      (wi.current_end - wi.current_start) AS wi_duration
    FROM work_items wi
    JOIN phases ph ON wi.phase_id = ph.id
    JOIN projects pj ON ph.project_id = pj.id
    WHERE pj.program_id = p_program_id
    AND wi.status NOT IN ('Cancelled')
  ),
  ),
  
  -- Forward pass: Calculate Early Start (ES) and Early Finish (EF)
  forward_pass AS (
    -- Base case: tasks with no predecessors
    SELECT 
      pwi.wi_id,
      pwi.wi_external_id,
      pwi.wi_current_start AS early_start,
      pwi.wi_current_end AS early_finish,
      pwi.wi_duration,
      0 AS depth
    FROM program_work_items pwi
    WHERE pwi.wi_id NOT IN (
      SELECT d.successor_item_id FROM dependencies d
      WHERE d.predecessor_item_id IN (SELECT pwi2.wi_id FROM program_work_items pwi2)
    )
    
    UNION ALL
    
    -- Recursive case: calculate ES = max(EF of all predecessors) + lag
    SELECT 
      pwi.wi_id,
      pwi.wi_external_id,
      GREATEST(
        pwi.wi_current_start,
        (fp.early_finish + COALESCE(d.lag_days, 0))
      ) AS early_start,
      GREATEST(
        pwi.wi_current_start,
        (fp.early_finish + COALESCE(d.lag_days, 0))
      ) + pwi.wi_duration AS early_finish,
      pwi.wi_duration,
      fp.depth + 1
    FROM program_work_items pwi
    JOIN dependencies d ON pwi.wi_id = d.successor_item_id
    JOIN forward_pass fp ON d.predecessor_item_id = fp.wi_id
    WHERE fp.depth < 100  -- Prevent infinite recursion
  ),
  
  -- Get max early finish per task (handles multiple predecessors)
  forward_max AS (
    SELECT 
      fp.wi_id,
      fp.wi_external_id,
      MAX(fp.early_start) AS early_start,
      MAX(fp.early_finish) AS early_finish,
      MAX(fp.wi_duration) AS wi_duration
    FROM forward_pass fp
    GROUP BY fp.wi_id, fp.wi_external_id
  ),
  
  -- Find project end date
  project_end AS (
    SELECT MAX(fm.early_finish) AS end_date FROM forward_max fm
  ),
  
  -- Backward pass: Calculate Late Start (LS) and Late Finish (LF)
  backward_pass AS (
    -- Base case: tasks with no successors (end tasks)
    SELECT 
      fm.wi_id,
      fm.wi_external_id,
      fm.early_start,
      fm.early_finish,
      (SELECT pe.end_date FROM project_end pe) - fm.wi_duration AS late_start,
      (SELECT pe.end_date FROM project_end pe) AS late_finish,
      fm.wi_duration,
      0 AS depth
    FROM forward_max fm
    WHERE fm.wi_id NOT IN (
      SELECT d.predecessor_item_id FROM dependencies d
      WHERE d.successor_item_id IN (SELECT pwi.wi_id FROM program_work_items pwi)
    )
    
    UNION ALL
    
    -- Recursive case: calculate LF = min(LS of all successors) - lag
    SELECT 
      fm.wi_id,
      fm.wi_external_id,
      fm.early_start,
      fm.early_finish,
      LEAST(
        bp.late_start - COALESCE(d.lag_days, 0)
      ) - fm.wi_duration AS late_start,
      LEAST(
        bp.late_start - COALESCE(d.lag_days, 0)
      ) AS late_finish,
      fm.wi_duration,
      bp.depth + 1
    FROM forward_max fm
    JOIN dependencies d ON fm.wi_id = d.predecessor_item_id
    JOIN backward_pass bp ON d.successor_item_id = bp.wi_id
    WHERE bp.depth < 100
  ),
  
  -- Get min late start per task (handles multiple successors)
  backward_min AS (
    SELECT 
      bp.wi_id,
      bp.wi_external_id,
      MIN(bp.early_start) AS early_start,
      MIN(bp.early_finish) AS early_finish,
      MIN(bp.late_start) AS late_start,
      MIN(bp.late_finish) AS late_finish
    FROM backward_pass bp
    GROUP BY bp.wi_id, bp.wi_external_id
  )
  
  -- Final result: Calculate float and identify critical path
  SELECT 
    bm.wi_id AS work_item_id,
    bm.wi_external_id AS external_id,
    bm.early_start,
    bm.early_finish,
    bm.late_start,
    bm.late_finish,
    (bm.late_start - bm.early_start)::int AS total_float,
    (bm.late_start - bm.early_start) = 0 AS is_critical
  FROM backward_min bm;
END;
$$ LANGUAGE plpgsql;

-- Function to update work items with calculated slack
CREATE OR REPLACE FUNCTION update_work_item_slack(p_program_id uuid)
RETURNS int AS $$
DECLARE
  updated_count int;
BEGIN
  WITH critical_path AS (
    SELECT * FROM calculate_critical_path(p_program_id)
  )
  UPDATE work_items wi
  SET 
    slack_days = cp.total_float,
    is_critical_path = cp.is_critical,
    updated_at = now()
  FROM critical_path cp
  WHERE wi.id = cp.work_item_id;
  
  GET DIAGNOSTICS updated_count = ROW_COUNT;
  RETURN updated_count;
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 9: Circular Dependency Detection
-- ==========================================

CREATE OR REPLACE FUNCTION detect_circular_dependencies(p_program_id uuid)
RETURNS TABLE (
  cycle_path text[],
  cycle_description text
) AS $$
BEGIN
  RETURN QUERY
  WITH RECURSIVE 
  program_deps AS (
    -- Get dependencies for work items in this program
    SELECT 
      d.predecessor_item_id AS pred_id, 
      d.successor_item_id AS succ_id, 
      wi.external_id AS wi_ext_id
    FROM dependencies d
    JOIN work_items wi ON d.successor_item_id = wi.id
    JOIN phases ph ON wi.phase_id = ph.id
    JOIN projects pj ON ph.project_id = pj.id
    WHERE pj.program_id = p_program_id
  ),
  
  dep_chain AS (
    -- Start from each dependency
    SELECT 
      pd.pred_id,
      pd.succ_id,
      ARRAY[pd.pred_id::text, pd.succ_id::text] AS path,
      false AS is_cycle
    FROM program_deps pd
    
    UNION ALL
    
    -- Follow the chain
    SELECT 
      dc.pred_id,
      pd.succ_id,
      dc.path || pd.succ_id::text,
      pd.succ_id = dc.pred_id AS is_cycle
    FROM dep_chain dc
    JOIN program_deps pd ON dc.succ_id = pd.pred_id
    WHERE NOT dc.is_cycle
    AND array_length(dc.path, 1) < 50  -- Prevent infinite recursion
    AND NOT pd.succ_id::text = ANY(dc.path)  -- Don't revisit
  )
  
  SELECT 
    dc.path AS cycle_path,
    'Circular dependency detected: ' || array_to_string(dc.path, ' -> ') AS cycle_description
  FROM dep_chain dc
  WHERE dc.is_cycle;
END;
$$ LANGUAGE plpgsql;


-- ==========================================
-- STEP 10: Auto-update timestamp trigger
-- ==========================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS work_items_updated_at ON work_items;
CREATE TRIGGER work_items_updated_at
BEFORE UPDATE ON work_items
FOR EACH ROW
EXECUTE FUNCTION update_updated_at();


-- ==========================================
-- GRANT PERMISSIONS (for Supabase)
-- ==========================================
GRANT ALL ON audit_logs TO authenticated;
GRANT ALL ON import_batches TO authenticated;
GRANT ALL ON baseline_versions TO authenticated;
GRANT SELECT ON resource_utilization TO authenticated;


-- ==========================================
-- MIGRATION COMPLETE
-- ==========================================
-- Run verification:
-- SELECT * FROM pg_indexes WHERE tablename = 'work_items';
-- SELECT * FROM resource_utilization LIMIT 5;
-- SELECT uuid_generate_v7();


-- ==========================================
-- STEP 11: Date Propagation Function
-- ==========================================

-- Function to propagate dates through dependency chain
CREATE OR REPLACE FUNCTION propagate_dependency_dates(p_program_id uuid)
RETURNS int AS $$
DECLARE
  updated_count int := 0;
  iteration_count int := 0;
  max_iterations int := 50;
BEGIN
  -- Iteratively propagate dates until no more changes
  LOOP
    iteration_count := iteration_count + 1;
    
    -- Update successor start dates based on predecessor end dates
    WITH date_updates AS (
      SELECT DISTINCT
        wi.id,
        wi.external_id,
        GREATEST(
          wi.current_start,
          MAX(pred.current_end + (d.lag_days || ' days')::interval + interval '1 day')
        )::date as new_start,
        wi.current_end,
        (wi.current_end - wi.current_start) as duration
      FROM work_items wi
      JOIN dependencies d ON wi.id = d.successor_item_id
      JOIN work_items pred ON d.predecessor_item_id = pred.id
      JOIN phases ph ON wi.phase_id = ph.id
      JOIN projects pj ON ph.project_id = pj.id
      WHERE pj.program_id = p_program_id
      AND wi.status NOT IN ('Cancelled', 'Completed')
      AND wi.actual_start IS NULL  -- Only update tasks that haven't started
      GROUP BY wi.id, wi.external_id, wi.current_start, wi.current_end
      HAVING MAX(pred.current_end + (d.lag_days || ' days')::interval + interval '1 day')::date > wi.current_start
    )
    UPDATE work_items wi
    SET 
      current_start = du.new_start,
      current_end = du.new_start + du.duration,
      updated_at = now()
    FROM date_updates du
    WHERE wi.id = du.id;
    
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    
    -- Exit if no more updates or max iterations reached
    EXIT WHEN updated_count = 0 OR iteration_count >= max_iterations;
  END LOOP;
  
  RETURN iteration_count;
END;
$$ LANGUAGE plpgsql;
