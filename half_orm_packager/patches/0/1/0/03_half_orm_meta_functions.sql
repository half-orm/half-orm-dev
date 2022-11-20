create or replace function half_orm_meta.check_database(old_dbid text default null) returns text as $$
DECLARE
    dbname text;
    dbid text;
BEGIN
    select current_database() into dbname;
    --XXX: use a materialized view.
    select encode(hmac(dbname, pg_read_file('hop_key'), 'sha1'), 'hex') into dbid;
    if old_dbid is not null and old_dbid != dbid
    then
        raise Exception 'Not the same database!';
    end if;
    return dbid;
END;
$$ language plpgsql;
