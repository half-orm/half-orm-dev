alter table half_orm_meta.hop_release rename to release;
alter table half_orm_meta.release add column dbid text references half_orm_meta.database(id) on update cascade;
