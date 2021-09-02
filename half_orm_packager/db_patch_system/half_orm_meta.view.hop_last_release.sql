create view "half_orm_meta.view".hop_last_release as
select * from half_orm_meta.hop_release order by major desc, minor desc, patch desc, pre_release desc, pre_release_num desc limit 1;
