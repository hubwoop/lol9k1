-- Built-in brackets: one row per match of an event's single elimination bracket.
-- Only first round matches store their teams (null is a bye), the teams of later
-- rounds are the winners of the matches before them.
create table matches
(
  id       integer primary key autoincrement not null,
  event    integer                           not null,
  round    integer                           not null,
  position integer                           not null,
  team1    integer                           null,
  team2    integer                           null,
  score1   integer                           null,
  score2   integer                           null,
  constraint matches_events_id_fk foreign key (event) references events (id),
  constraint matches_team1_fk foreign key (team1) references teams (id),
  constraint matches_team2_fk foreign key (team2) references teams (id),
  constraint matches_event_round_position_uindex unique (event, round, position)
);
