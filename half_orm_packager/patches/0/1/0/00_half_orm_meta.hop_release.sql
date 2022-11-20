create table half_orm_meta.hop_release (
    id gen_random_uuid(),
    major integer not null,
    minor integer not null,
    patch integer not null,
    pre_release text default '' check (pre_release in ('alpha', 'beta', 'rc', 'next', '')),
    pre_release_num text default '' check (pre_release_num = ''::text OR pre_release_num ~ '^\d+$'::tex
t)
);
