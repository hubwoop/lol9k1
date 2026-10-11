-- Invites can grant admin rights (70a1aff, 2023).
alter table invites add column admin integer default 0 not null;
