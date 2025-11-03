SELECT now() AS current_time,
       current_database(),
       current_user,
       count(*) AS total_tables
FROM information_schema.tables
WHERE table_schema = 'public';
