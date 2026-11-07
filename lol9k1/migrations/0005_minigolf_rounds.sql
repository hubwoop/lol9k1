-- Finished minigolf rounds, for the leaderboard.
-- The total of a round is computed from its strokes, so the two can't disagree.
-- The check only makes sure strokes is a JSON array. That its items are stroke counts, and
-- that there's one per hole, is validated by the app (minigolf.submit_round_api), the only writer.
create table minigolf_rounds
(
  id        integer primary key autoincrement,
  user      integer not null,
  course    text    not null,
  strokes   text    not null check (json_valid(strokes) and json_type(strokes) = 'array'), -- per hole, e.g. [3,2,4]
  played_at text    not null,
  constraint minigolf_rounds_users_id_fk foreign key (user) references users (id)
);
create index minigolf_rounds_course_user_index
  on minigolf_rounds (course, user);
