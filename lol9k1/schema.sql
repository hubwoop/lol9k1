pragma foreign_keys = on;

-- GAMES
drop table if exists games;
create table games (
  id          integer primary key autoincrement,
  name        text    not null unique,
  slug        text    not null unique,
  max_players integer,
  description text,
  no_drm      integer null,
  available   integer null,
  low_spec    integer null,
  added_by    integer not null,
  igdb_id     integer,
  constraint games_users_id_fk foreign key (added_by) references users (id)
);
create unique index games_id_uindex
  on games (id);

-- USERS
drop table if exists users;
create table users (
  id         integer primary key autoincrement,
  name       text not null unique,
  email      text,
  password   text not null,
  gender     text,
  is_admin   integer,
  token_used text,
  constraint users_invites_token_fk foreign key (token_used) references invites (token)
);
create unique index users_id_uindex
  on users (id);
create unique index users_token_used_uindex
  on users (token_used);
-- VOTES
drop table if exists votes;
create table votes
(
  user integer not null,
  game integer not null,
  vote integer,
  constraint votes_user_game_pk primary key (user, game),
  constraint votes_users_id_fk foreign key (user) references users (id),
  constraint votes_games_id_fk foreign key (game) references games (id),
  unique (user, game)
);

-- INVITES
drop table if exists invites;
create table invites
(
  token    text primary key not null,
  used     integer default 0 not null,
  added_by integer          not null,
  constraint invites_users_id_fk foreign key (added_by) references users (id)
);
create unique index invites_token_uindex
  on invites (token);

-- TOURNAMENTS
drop table if exists events;
create table events
(
  id                integer primary key autoincrement not null,
  game              integer                           not null,
  start_datetime    integer                           not null,
  end_datetime      integer                           not null,
  created_by        integer                           not null,
  mode              text                              not null,
  state             text                              null,
  description       text                              null,
  external_url      text                              null,
  pick_order        text                              null,
  currently_picking integer                           null,
  skips             integer default 0 not null,
  constraint game_of_event_fk foreign key (game) references games (id),
  constraint creator_user_fk foreign key (created_by) references users (id),
  constraint user_that_is_picking_fk foreign key (currently_picking) references users (id)
);
create unique index events_id_uindex
  on events (id);

-- TEAMS
drop table if exists teams;
create table teams
(
  id      integer primary key autoincrement not null,
  name    text,
  captain integer                           not null
);
create unique index teams_id_uindex
  on teams (id);

-- TOURNAMENT PARTICIPANTS
drop table if exists tournament_participants;
create table tournament_participants
(
  user            int not null,
  tournament      int not null,
  team            int,
  is_team_captain int,
  constraint tournament_participants_tournaments_id_fk foreign key (tournament) references events (id),
  constraint tournament_participants_users_id_fk foreign key (user) references users (id),
  constraint tournament_participants_teams_id_fk foreign key (team) references teams (id)
);

-- CONFIG
drop table if exists config;
create table config
(
  key   text not null primary key,
  value text
);
create unique index config_key_uindex
  on config (key);


