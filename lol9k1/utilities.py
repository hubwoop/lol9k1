from collections import namedtuple

NAVY_SEAL = "no."
MODE_INT_TO_STRING = {
    1: 'Single Elimination',
    2: 'Double Elimination'
}
GENDER_INT_TO_STRING = {
    0: "😐",
    1: "🚹",
    2: "🚺",
    3: "🚁"
}

FlashCategories = namedtuple('flash_type', ['message', 'error', 'warning', 'success'])
STYLE = FlashCategories('primary', 'danger', 'warning', 'success')
