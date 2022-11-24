create table half_orm_meta.hop_release (
    id uuid default gen_random_uuid() primary key,
    major integer not null,
    minor integer not null,
    patch integer not null,
    pre_release text default '' check (pre_release in ('alpha', 'beta', 'rc', 'next', '')),
    pre_release_num text default '' check (pre_release_num = ''::text OR pre_release_num ~ '^\d+$'::text)
);

alter table half_orm_meta.release add column hop_release_id uuid references half_orm_meta.hop_release(id);
