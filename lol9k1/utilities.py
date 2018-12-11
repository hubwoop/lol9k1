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

flash_categories = namedtuple('flash_type', ['message', 'error', 'warning', 'success'])
STYLE = flash_categories('primary', 'danger', 'warning', 'success')
