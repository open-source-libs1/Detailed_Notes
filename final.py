-- Find which table(s) in a schema contain ONE specific column
select
  c.table_schema,
  c.table_name,
  c.column_name,
  c.data_type
from information_schema.columns c
where lower(c.table_schema) = lower('CompEngineMicroServiceOutput_QA')   -- <-- your schema
  and lower(c.column_name)  = lower('YOUR_COLUMN_NAME')                 -- <-- your column
order by c.table_name, c.ordinal_position;
