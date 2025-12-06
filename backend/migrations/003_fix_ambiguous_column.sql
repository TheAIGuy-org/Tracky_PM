-- ==========================================
-- MIGRATION 003: Fix Ambiguous Column References
-- ==========================================
-- Fixes: "column reference 'external_id' is ambiguous" error
-- in critical path calculation functions
-- ==========================================

-- Drop and recreate the calculate_critical_path function with explicit table aliases
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


-- Update the slack update function to work with the fixed function
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


-- Fix detect_circular_dependencies as well (uses external_id)
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
