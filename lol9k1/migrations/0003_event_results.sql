-- Match results: where each team of an event finished, 1 = winner. Ties share a placement.
create table event_results
(
  event     integer not null,
  team      integer not null,
  placement integer not null check (placement >= 1),
  constraint event_results_pk primary key (event, team),
  constraint event_results_events_id_fk foreign key (event) references events (id),
  constraint event_results_teams_id_fk foreign key (team) references teams (id)
);

-- Order in which players were picked in an event's pick phase, 1 = first pick.
-- Null for captains and for players picked before this column existed.
alter table tournament_participants add column pick_number integer null;
