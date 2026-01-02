-- Finds tables in a schema that contain ALL the columns you specify
with wanted_cols as (
  select lower(col) as col_name
  from (
    select 'col1' as col union all
    select 'col2' union all
    select 'col3'
    -- add/remove rows as needed
  ) x
)
select
  c.table_schema,
  c.table_name
from information_schema.columns c
join wanted_cols w
  on lower(c.column_name) = w.col_name
where lower(c.table_schema) = lower('CompEngineMicroServiceOutput_QA')  -- change schema if needed
group by c.table_schema, c.table_name
having count(distinct w.col_name) = (select count(*) from wanted_cols)
order by c.table_schema, c.table_name;
