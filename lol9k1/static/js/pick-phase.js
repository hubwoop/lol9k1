/*
<div class="row">
    <div class="col-6">
      <ul id="state">
      </ul>
    </div>
    <div class="col-6">
      <ul id="possible-teammates">
      </ul>
      <button onclick="skip_pick()" class="btn btn-sm btn-primary" id="skipper">Skip</button>
    </div>
  </div>
 */
class TeamPicker extends HTMLElement {
    constructor() {
        super();this.pick_button()
        this.create_ui();

        this.previous_states = [];
        this.current_state = undefined;
        this.currently_possible_users = undefined;
        this.event_id = this.getAttribute('data-event-id'); //{{ event_id|safe }};
        this.stateApiEndpoint = this.getAttribute('data-event-api-url'); // {{ url_for('event.get_state_api', event_id=event_id) }}
        this.possible_teammates_api = this.getAttribute('data-possible-teammates-api-url'); // {{ url_for('event.get_possible_teammates_api', event_id=event_id) }}
        this.event_url = this.getAttribute('data-event-url');//{{ url_for('event.event', event_id=event_id)}}
        this.names_being_edited = [];
        this.leading = [];
        this.fetch_teams_user_is_captain_of();

        this.refresh_view();
        setInterval(this.refresh_view, 500);
    }

    create_ui() {
        const shadow = this.attachShadow({mode: 'open'});

        const main_row = document.createElement('div');
        main_row.classList.add('row');

        this.create_state_ui(main_row);
        const team_picker_col = this.create_team_picker_ui();

        main_row.appendChild(team_picker_col);
        shadow.appendChild(main_row);
    }

    create_team_picker_ui() {
        /*
           <div class="col-6"> team_picker_col
            <ul id="possible-teammates"></ul>
            this.skip_button: <button onclick="skip_pick()" class="btn btn-sm btn-primary">Skip</button>
           </div>
        */
        const team_picker_col = document.createElement('div');

        this.possible_teammates_list = document.createElement('ul');

        team_picker_col.appendChild(this.possible_teammates_list);

        this.skip_button = document.createElement('button');
        this.skip_button.onclick = this.skip_pick;
        this.skip_button.classList.add('btn', 'btn-sm', 'btn-primary');
        this.skip_button.innerText = 'Skip';

        team_picker_col.appendChild(this.skip_button);
        return team_picker_col;
    }

    create_state_ui(main_row) {
        /*
            <div class="col-6">
             this.state_list: <ul></ul>
            </div>
         */
        this.state_list = document.createElement('ul');
        const state_col = document.createElement('div');
        state_col.appendChild(this.state_list);
        main_row.appendChild(state_col);
    }

    fetch_teams_user_is_captain_of() {
        fetch(`/event/${this.event_id}/captain-of`, {
            method: 'POST',
            headers: new Headers({
                'Content-Type': 'application/json'
            }),
            credentials: 'include'
        })
            .then(response => response.json())
            .catch(error => console.error('Error:', error))
            .then(response => this.leading = response)
            .finally(response => console.log('Assigned leading teams:', response))
    }


    refresh_view() {
        this.update_possible_teammates();
        this.update_state();
    }

    initialize_team_states() {
        this.current_state.teams.forEach(this.initialize_team_state);
        console.log("initialized team state");
    }

    initialize_team_state(team) {
        let teams_list_item = document.createElement("li");
        teams_list_item.id = `team-${team.team_id}`;
        let team_name = document.createElement('h5');
        let team_name_title;
        if (team.name == null) {
            team_name_title = `Team #${team.team_id}`;
        } else {
            team_name_title = `Team ${team.name}`;
        }
        team_name_title = document.createTextNode(team_name_title);

        team_name.onclick = this.listenForDoubleClick(team_name, team.team_id);
        team_name.appendChild(team_name_title);
        teams_list_item.appendChild(team_name);
        const team_members_list = document.createElement("ul");
        team.players.forEach(player => this.insert_teammate(player, team_members_list, teams_list_item));

        if (team.team_id === this.current_state.pick_details.currently_picking) {
            teams_list_item.classList.add('isPicking');
            if (this.leading.includes(team.team_id)) {
                console.log("It's your turn.");
                this.enable_possible_teammate_picking();
            } else {
                console.log("It's not your turn.");
                this.disable_possible_teammate_picking();
            }
        }

        this.state_list.appendChild(teams_list_item);
    }

    insert_teammate(team_member, team_members_list, teams_list_item) {
        let team_member_item = document.createElement("li");
        let team_member_item_content;
        if (team_member === team.captain) {
            team_member_item_content = document.createTextNode(`${team_member} 👑`);
        } else {
            team_member_item_content = document.createTextNode(team_member);
        }
        team_member_item.appendChild(team_member_item_content);
        team_members_list.appendChild(team_member_item);
        teams_list_item.appendChild(team_members_list);
    }

    update_state() {
        fetch(this.stateApiEndpoint)
            .then((response) => response.json())
            .then(self.handle_end_of_pick_phase)
            .then((fetched_state) => {
                console.log("Fetched State", fetched_state);
                if (JSON.stringify(fetched_state) !== JSON.stringify(this.current_state)) {
                    this.apply_state_change(fetched_state);
                }
            });
    }

    handle_end_of_pick_phase(fetched_state) {
        if ('state' in fetched_state && fetched_state.state !== "pickphase") {
            window.location.assign(this.event_url);
        }
    }

    apply_state_change(fetched_state) {

        this.previous_states.push(this.current_state);
        this.current_state = fetched_state;

        if (!this.current_state) {
            this.initialize_team_states();
        } else {
            if (JSON.stringify(fetched_state.teams) !== JSON.stringify(this.current_state.teams)) {
                this.update_team_states(fetched_state);
            }
            if (JSON.stringify(fetched_state.pick_details !== JSON.stringify(this.current_state.pick_details))) {
                this.update_pick_details(fetched_state);
            }
            console.log("updated state.")
        }
    }

    update_pick_details(fetched_state) {
        let picking_team = document.getElementsByClassName('isPicking')[0];
        picking_team.classList.remove('isPicking');

        picking_team = document.getElementById(`team-${fetched_state.pick_details.currently_picking}`);
        picking_team.classList.add('isPicking');
        if (this.leading.includes(fetched_state.pick_details.currently_picking)) {
            console.log("Du bist dran.");
            this.enable_possible_teammate_picking();
        } else {
            console.log("Du bist nicht dran.");
            this.disable_possible_teammate_picking();
        }
        console.log("pick details changed");
    }

    update_team_states(fetched_state) {
        fetched_state.teams.forEach((fetched_team) => {
            let current_team = this.current_state.teams.filter((team) => {
                return team.team_id === fetched_team.team_id
            });
            current_team = current_team[0]; // since we use unique IDs this should be safe
            if (JSON.stringify(current_team.players) !== JSON.stringify(fetched_team.players)) {
                // https://stackoverflow.com/a/33034768
                let removed_teammates = current_team.players.filter(x => !fetched_team.players.includes(x));
                let added_teammates = fetched_team.players.filter(x => !current_team.players.includes(x));
                if (removed_teammates.length > 0) {
                    //removed_teammates.forEach(); // TODO
                }
                if (added_teammates.length > 0) {
                    added_teammates.forEach(function (teammates_name) {
                        let team_member_item = document.createElement("li");
                        let team_member_item_content = document.createTextNode(teammates_name);
                        team_member_item.appendChild(team_member_item_content);
                        let teams_list_item = document.getElementById(`team-${fetched_team.team_id}`);
                        let teams_list = teams_list_item.getElementsByTagName('ul')[0];
                        teams_list.appendChild(team_member_item);
                        console.log(`Team ${fetched_team.team_id} has a new player: ${teammates_name}`)
                    });
                }
            }
        });
        console.log("teams changed")
    }

    add_to_possible_teammate_list(user) {
        let user_list_item = document.createElement("li");
        user_list_item.id = `possible-teammate-${user.id}`;
        let item_text_content = document.createTextNode(`${user.gender} ${user.name}`);
        user_list_item.appendChild(item_text_content);
        user_list_item.appendChild(this.pick_button());
        this.possible_teammates_list.appendChild(user_list_item);
    }

    pick_button() {
        let pick_user_button = document.createElement('button');
        let pick_user_button_text = document.createTextNode('❤️');
        pick_user_button.appendChild(pick_user_button_text);
        pick_user_button.onclick = () => this.add_teammate(user.id);
        pick_user_button.classList.add("btn", "btn-primary", "btn-sm");
        return pick_user_button;
    }

    add_teammate(user_id) {
        fetch(`/event/${this.event_id}/team/${this.current_state.pick_details.currently_picking}/add-mate`, {
            method: 'POST',
            body: JSON.stringify(user_id),
            headers: new Headers({
                'Content-Type': 'application/json'
            }),
            credentials: 'include'
        }).then(res => res.json())
            .catch(error => console.error('Error:', error))
            .then(function (response) {
                    console.log('Success:', response);
                }
            );
    }

    remove_from_possible_teammate_list(user) {
        this.possible_teammates_list
            .removeChild(document.getElementById(`possible-teammate-${user.id}`))
    }

    disable_possible_teammate_picking() {
        let possible_teammates = this.possible_teammates_list;
        let all_buttons = possible_teammates.getElementsByClassName("btn");
        if (all_buttons.length > 0) {
            for (let button of all_buttons) {
                button.disabled = true;
            }
        }
        this.skip_button.disabled = true;
    }

    enable_possible_teammate_picking() {
        let all_buttons = this.possible_teammates_list.getElementsByClassName("btn");
        if (all_buttons.length > 0) {
            for (let button of all_buttons) {
                button.disabled = false;
            }
        }
        this.skip_button.disabled = false;
    }

    update_possible_teammates() {
        fetch(this.possible_teammates_api)
            .then((response) => response.json())
            .then((fetched_users) => {

                if (JSON.stringify(fetched_users) !== JSON.stringify(this.currently_possible_users)) {

                    if (!this.currently_possible_users) {
                        console.log('init possible teammates');
                        this.currently_possible_users = fetched_users;
                        fetched_users.forEach(this.add_to_possible_teammate_list.bind(this));
                        return;
                    }

                    // https://stackoverflow.com/a/33034768
                    let removed_users = this.currently_possible_users.filter(x => !fetched_users.includes(x));
                    let added_users = fetched_users.filter(x => !this.currently_possible_users.includes(x));
                    removed_users.forEach(this.remove_from_possible_teammate_list);
                    added_users.forEach(this.add_to_possible_teammate_list);

                    //const user_list_item = document.createElement("p");
                    //document.getElementById('possbile-teammates').appendChild(`<li>${element.name}</li>`);
                    this.currently_possible_users = fetched_users;
                    console.log("updated possible users!");
                    console.log(this.currently_possible_users)
                }
            });
    }

    listenForDoubleClick(element, team_id) {

        //TODO: check if authorized...
        if (this.names_being_edited.includes(element)) {
            return
        }
        element.contentEditable = true;
        this.names_being_edited.push(element);
        if (element.textContent.startsWith("Team ")) {
            element.textContent = element.textContent.slice(5); //removes the "team " prefix
        }
        const old_content = element.textContent;
        let name_update_check = setInterval(() => {
            if (document.activeElement !== element) {
                element.contentEditable = false;
                if (old_content !== element.textContent) {
                    this.update_team_name(team_id, element.textContent)
                }
                clearInterval(name_update_check);
                this.names_being_edited = this.names_being_edited.filter(item => item !== element);
                element.textContent = `Team ${element.textContent}`;
            }
        }, 300);
    }

    update_team_name(team_id, new_team_name) {
        fetch(`/team/${team_id}/name`, {
            method: 'POST',
            body: JSON.stringify(new_team_name),
            headers: new Headers({
                'Content-Type': 'application/json'
            }),
            credentials: 'include'
        }).then(res => res.json())
            .catch(error => console.error('Error:', error))
            .then(response => console.log('Success:', response));
    }

    skip_pick() {
        fetch(`/event/${this.event_id}/team/${this.current_state.pick_details.currently_picking}/skip`, {
            method: 'POST',
            headers: new Headers({
                'Content-Type': 'application/json'
            }),
            credentials: 'include'
        }).then(res => res.json())
            .catch(error => console.error('Error:', error))
            .then(function (response) {
                    console.log('Success:', response);
                }
            );
    }
}

customElements.define('team-picker', TeamPicker);