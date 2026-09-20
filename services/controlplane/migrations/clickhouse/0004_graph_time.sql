ALTER TABLE agent_run_graphs
ADD COLUMN IF NOT EXISTS occurred_at DateTime64(9, 'UTC') DEFAULT updated_at
