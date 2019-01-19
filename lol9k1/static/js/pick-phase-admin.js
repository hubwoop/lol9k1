/*
  {% if session.get('user_id') == event.creator_id or session.get('is_admin') %}
    <div class="row">
      <div class="col-auto">
        <h3>Tourney owner options:</h3>
        <a href="{{ url_for('event.stop_pick_phase', event_id=event_id) }}" class="btn btn-primary">End pick phase</a>
        <button class="btn btn-warning btn-sm" onclick="skip_pick()">Force skip</button>
      </div>
    </div>
  {% endif %}
 */
class TeamPickerAdmin extends HTMLElement {
    constructor() {
        super();
        const shadow = this.attachShadow({mode: 'open'});
    }
}