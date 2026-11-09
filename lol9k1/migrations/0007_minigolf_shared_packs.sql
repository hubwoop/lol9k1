-- Minigolf map packs shared by players, built in the map editor. Everybody can browse, test and play them.
-- A pack's holes never change once published: an update is a new version, so rounds and running games
-- keep the holes they were played on. Rounds and games refer to a version as their course, 'pack:<version id>',
-- every version has a Hall of Fame of its own.
-- A withdrawn pack isn't offered anymore, but its versions stay for the games and rounds played on them.
create table minigolf_packs
(
  id         integer primary key autoincrement,
  author     integer not null,
  name       text    not null,
  hint       text    not null default '',
  based_on   integer,          -- the shared pack it was made from in the editor, if any
  version    integer,          -- the current version, minigolf_pack_versions.id
  status     text    not null default 'listed' check (status in ('listed', 'withdrawn')),
  created_at text    not null,
  updated_at text    not null,
  constraint minigolf_packs_users_id_fk foreign key (author) references users (id),
  constraint minigolf_packs_based_on_fk foreign key (based_on) references minigolf_packs (id)
);
create index minigolf_packs_author_index
  on minigolf_packs (author);

-- The holes are validated and rebuilt by the app (minigolf_packs.validate_holes), the only writer.
create table minigolf_pack_versions
(
  id           integer primary key autoincrement,
  pack         integer not null,
  number       integer not null, -- 1, 2, ... per pack
  holes        text    not null check (json_valid(holes) and json_type(holes) = 'array'),
  hole_count   integer not null,
  par          integer not null, -- of all holes together
  published_at text    not null,
  constraint minigolf_pack_versions_pack_number_unique unique (pack, number),
  constraint minigolf_pack_versions_packs_id_fk foreign key (pack) references minigolf_packs (id)
);
