from typing import Union

import dateutil
from slugify import slugify

from . import utilities


def register_on(app):
    @app.template_filter('strftime')
    def format_date_time_string(date: str, fmt=None) -> str:
        date = dateutil.parser.parse(date)
        native = date.replace(tzinfo=None)
        the_format = '%d.%m.%y <strong>%H:%M</strong>'
        return native.strftime(the_format)

    @app.template_filter('gender')
    def translate_gender(gender: Union[int, str], fmt=None) -> str:
        return utilities.GENDER_INT_TO_STRING[int(gender)]

    @app.template_filter('slugify')
    def translate_gender(string: str, fmt=None) -> str:
        return slugify(string)