from lol9k1.database import get_db


def select_start_page(without_users_vote=False, order_by_score=False):
    without_users_vote = 'where voted.vote isnull' if without_users_vote else ''
    order_by_score = 'score desc' if order_by_score else 'games.name asc'
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
  left join votes voted on games.id = voted.game and voted.user = ? {without_users_vote}
group by games.id
order by {order_by_score}
'''


def delete_game(game_id):
    db = get_db()
    game = db.execute('select name from games where id = ?', [game_id]).fetchone()[0]
    db.executescript('delete from votes where game = ?;'
                     'delete from events where game = ?;'
                     'delete from games where id = ?;', [game_id, game_id, game_id])
    db.commit()
    return game
