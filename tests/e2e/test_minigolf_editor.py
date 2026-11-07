"""The minigolf map editor: build holes, test play them and export them as code."""
import json

from playwright.sync_api import Page, expect

from conftest import login
from test_minigolf import putt


def open_editor(page: Page) -> None:
    page.goto('/minigolf/editor')
    expect(page.locator('#mgeHoles li').first).to_be_visible()


def click(page: Page, x: float, y: float) -> None:
    """Clicks the editor's canvas in course coordinates."""
    box = page.locator('.mgeOverlay').bounding_box()
    scale = box['width'] / 640
    page.mouse.click(box['x'] + x * scale, box['y'] + y * scale)


def drag(page: Page, from_x: float, from_y: float, to_x: float, to_y: float) -> None:
    box = page.locator('.mgeOverlay').bounding_box()
    scale = box['width'] / 640
    page.mouse.move(box['x'] + from_x * scale, box['y'] + from_y * scale)
    page.mouse.down()
    page.mouse.move(box['x'] + to_x * scale, box['y'] + to_y * scale, steps=5)
    page.mouse.up()


def hole(page: Page) -> dict:
    return page.evaluate('lol9k1MinigolfEditor.pack.holes[lol9k1MinigolfEditor.current]')


def checks(page: Page):
    return page.get_by_role('list', name='Checks')


def new_hole(page: Page) -> None:
    """A hole with a rect(60, 100, 520, 200) outline, the tee at 110, 200 and the cup at 530, 200."""
    page.get_by_role('button', name='+ New hole').click()


def test_the_editor_is_linked_from_minigolf_and_starts_with_the_classic_pack(page: Page, alice):
    login(page, alice)
    page.goto('/minigolf/')
    page.get_by_role('link', name='🛠 Map editor').click()

    holes = page.get_by_role('list', name='Holes').get_by_role('button')
    expect(holes).to_have_count(9)
    expect(holes.first).to_have_text('Warm-up (par 2)')
    expect(holes.first).to_have_attribute('aria-current', 'true')
    expect(page.get_by_label('Name', exact=True).nth(1)).to_have_value('Warm-up')
    expect(checks(page)).to_have_text('All good.')

    page.get_by_label('Pack to load').select_option(label='Bumper Brawl')
    page.get_by_role('button', name='Load').click()
    expect(holes.first).to_have_text('Crossroads (par 3)')
    expect(checks(page)).to_have_text('All good, every tee is as good as the others.')
    # Load can be undone like anything else
    page.get_by_role('button', name='↶ Undo').click()
    expect(holes.first).to_have_text('Warm-up (par 2)')


def test_every_pack_reads_back_as_it_is_exported(page: Page, alice):
    login(page, alice)
    open_editor(page)
    result = page.evaluate('''() => {
        const T = lol9k1MinigolfEditorTools;
        // numbers are exported to 3 decimals, keys in an order of their own
        const canon = x => Array.isArray(x) ? x.map(canon)
            : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canon(x[k])]))
            : typeof x === 'number' ? Math.round(x * 1000) / 1000 : x;
        return Object.entries(lol9k1MinigolfPacks).map(([id, p]) => {
            const holes = p.holes.map(T.normalize);
            const code = T.packCode({id, name: id, hint: p.hint, holes});
            return [id, JSON.stringify(canon(T.importHoles(code))) === JSON.stringify(canon(holes))];
        });
    }''')
    assert result == [['classic', True], ['brawl', True]]


def test_place_a_bumper_drag_the_cup_and_export_the_hole(page: Page, alice):
    login(page, alice)
    open_editor(page)
    new_hole(page)
    expect(page.get_by_role('list', name='Holes').get_by_role('button')).to_have_count(10)

    page.get_by_role('button', name='Bumper', exact=True).click()
    click(page, 203, 148)
    # snapped to the grid, and selected to be edited
    expect(page.get_by_label('radius')).to_have_value('12')
    page.get_by_label('radius').fill('15')
    page.get_by_label('radius').press('Enter')
    drag(page, 530, 200, 400, 250)

    page.get_by_role('button', name='Copy hole').click()
    code = page.get_by_label('Exported code')
    expect(code).to_have_value('\n'.join([
        '        {',
        "            name: 'New hole', par: 3,",
        '            outline: rect(60, 100, 520, 200),',
        '            bumpers: [[200, 150, 15]],',
        '            start: [110, 200], cup: [400, 250],',
        '        },',
    ]))

    page.keyboard.press('Control+z')
    assert hole(page)['cup'] == [530, 200]
    page.keyboard.press('Control+Shift+z')
    assert hole(page)['cup'] == [400, 250]


def test_unfair_tees_are_pointed_out(page: Page, alice):
    login(page, alice)
    open_editor(page)
    new_hole(page)

    click(page, 110, 200)
    expect(page.locator('.mgeSelectedName')).to_have_text('Tee')
    page.get_by_role('button', name='Mirror copy left to right').click()
    assert hole(page)['starts'] == [[110, 200], [530, 200]]
    # the second tee is right on the cup
    expect(checks(page)).to_contain_text('Tee 2 is')

    click(page, 530, 200)
    page.get_by_label('x', exact=True).fill('320')
    page.get_by_label('x', exact=True).press('Enter')
    expect(checks(page)).to_have_text('All good, every tee is as good as the others.')

    page.get_by_role('button', name='Water', exact=True).click()
    click(page, 200, 150)
    expect(checks(page)).to_have_text("Tee 2 isn't as good as tee 1: mirrored left to right, "
                                      'the hole would be the same but for the water.')
    page.get_by_role('button', name='Mirror copy left to right').click()
    expect(checks(page)).to_have_text('All good, every tee is as good as the others.')


def test_a_test_run_plays_the_hole_and_saves_nothing(page: Page, seed, alice):
    login(page, alice)
    open_editor(page)
    page.get_by_role('button', name='▶ Test').click()
    expect(page.locator('#minigolf')).to_have_attribute('data-state', 'aim')
    expect(page.locator('#minigolfStatus')).to_contain_text("Player 1, it's your turn! Stroke 1.")

    # Warm-up is a straight lane, the cup is 420px to the right of the tee
    putt(page, 300, 200, -85, 0)

    expect(page.locator('#minigolfResult')).to_be_visible(timeout=20_000)
    expect(page.locator('#minigolfSaved')).to_have_text('A test run, nothing was saved.')
    assert seed.query('select * from minigolf_rounds') == []

    page.get_by_role('button', name='Play again').click()
    expect(page.locator('#minigolf')).to_have_attribute('data-state', 'aim')
    page.get_by_role('button', name='■ Stop test').click()
    expect(page.locator('#minigolfStatus')).to_have_text('Editing.')
    expect(page.locator('.mgeOverlay')).to_be_visible()


def test_holes_that_cant_be_played_cant_be_tested(page: Page, alice):
    login(page, alice)
    open_editor(page)
    new_hole(page)
    click(page, 110, 200)
    page.keyboard.press('Delete')
    expect(checks(page)).to_have_text('There is no tee.')
    page.get_by_role('button', name='▶ Test').click()
    expect(page.locator('#minigolfStatus')).to_have_text("Can't test this hole: There is no tee.")
    expect(page.locator('#minigolf')).to_have_attribute('data-state', 'setup')


def test_import_holes_as_they_are_written_in_minigolf_js(page: Page, alice):
    login(page, alice)
    open_editor(page)
    page.get_by_label('Code to import').fill('''
        {
            name: 'Pasted', par: 4,  // a comment
            outline: rect(40, 40, 560, 320),
            sand: [[100, 100, 50, 50]],
            starts: [[80, 200], [560, 200]], cup: [320, 200],
        },
    ''')
    page.get_by_role('button', name='Import').click()
    expect(page.locator('#mgeImportMessage')).to_have_text('Imported 1 hole.')
    holes = page.get_by_role('list', name='Holes').get_by_role('button')
    expect(holes.nth(1)).to_have_text('Pasted (par 4)')
    expect(holes.nth(1)).to_have_attribute('aria-current', 'true')
    assert hole(page)['sand'] == [[100, 100, 50, 50]]

    page.get_by_label('Code to import').fill('{name: "Broken", outline: ')
    page.get_by_role('button', name='Import').click()
    expect(page.locator('#mgeImportMessage')).to_contain_text("Couldn't import that")
    # code is read, never run
    page.get_by_label('Code to import').fill('alert(1)')
    page.get_by_role('button', name='Import').click()
    expect(page.locator('#mgeImportMessage')).to_contain_text("Couldn't import that")


def test_the_workspace_is_kept_in_the_browser(page: Page, alice):
    login(page, alice)
    open_editor(page)
    page.get_by_role('button', name='Dogleg (par 3)').click()
    page.get_by_label('Par').fill('5')
    page.get_by_label('Par').press('Enter')
    page.reload()

    expect(page.get_by_role('button', name='Dogleg (par 5)')).to_have_attribute('aria-current', 'true')
    stored = json.loads(page.evaluate("localStorage.getItem('minigolfEditor')"))
    assert stored['pack']['holes'][1]['par'] == 5
