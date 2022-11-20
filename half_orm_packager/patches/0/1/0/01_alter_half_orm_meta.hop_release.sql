alter table half_orm_meta.hop_release rename to half_orm_meta.release;
alter table half_orm_meta.release add column dbid text references half_orm_meta.database(id) on update cascade;
alter table half_orm_meta.release add column hop_release_id references half_orm_meta.hop_relase(id);