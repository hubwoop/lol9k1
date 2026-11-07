-- Minigolf games played across the network by registered players, each on their own computer.
-- A game is open for joining in the lobby until its host starts it, then it's played until finished.
create table minigolf_games
(
  id         integer primary key autoincrement,
  course     text    not null,
  host       integer not null,
  status     text    not null default 'lobby' check (status in ('lobby', 'playing', 'finished')),
  created_at text    not null,
  started_at text,
  constraint minigolf_games_users_id_fk foreign key (host) references users (id)
);
create index minigolf_games_status_index
  on minigolf_games (status);

-- The players of a game. Their seat (tee order on the first hole, colour) is the order they joined in.
create table minigolf_game_players
(
  id   integer primary key autoincrement,
  game integer not null,
  user integer not null,
  constraint minigolf_game_players_game_user_unique unique (game, user),
  constraint minigolf_game_players_games_id_fk foreign key (game) references minigolf_games (id) on delete cascade,
  constraint minigolf_game_players_users_id_fk foreign key (user) references users (id)
);

-- Everything that happens in a running game, in order. The state of a game (whose turn it is, where
-- the balls are, the scores) is replayed from its moves by the app (minigolf.replay), the only writer.
-- A shot carries how it was played and where every ball ended up, as reported by the shooter's browser.
-- A leave takes a player out of the game, either on their own or skipped by the others when idle.
-- (game, seq) is unique, so of two moves made at once only one gets in.
create table minigolf_moves
(
  game      integer not null,
  seq       integer not null, -- 0, 1, 2, ... per game
  user      integer not null, -- the shooter, or the player who left
  kind      text    not null check (kind in ('shot', 'leave')),
  data      text check (data is null or json_valid(data)),
  played_at text    not null,
  constraint minigolf_moves_pk primary key (game, seq),
  constraint minigolf_moves_games_id_fk foreign key (game) references minigolf_games (id) on delete cascade,
  constraint minigolf_moves_users_id_fk foreign key (user) references users (id)
);
