def select_start_page(without_users_vote=False, order_by_score=False):
    return f'''
select
  games.id,
  games.name,
  games.slug,
  games.max_players,
  games.description,
  games.no_drm,
  games.low_spec,
  games.available,
  users.name as added_by_user,
  sum(votes.vote) as score,
  voted.vote as this_sessions_user_vote
from games
  inner join votes on games.id = votes.game
  inner join users on games.added_by = users.id
  left join votes voted on games.id = voted.game and voted.user = ? {'where voted.vote isnull' if without_users_vote else ''}
group by games.id
order by {'score desc' if order_by_score else 'games.name asc'}
'''