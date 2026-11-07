-- Finished minigolf rounds, for the leaderboard.
create table minigolf_rounds
(
  id        integer primary key autoincrement,
  user      integer not null,
  course    text    not null,
  strokes   text    not null, -- strokes per hole, comma separated
  total     integer not null,
  played_at text    not null,
  constraint minigolf_rounds_users_id_fk foreign key (user) references users (id)
);
create index minigolf_rounds_course_total_index
  on minigolf_rounds (course, total);
