from typing import Union

import markdown as markdown_lib
from dateutil import parser as date_parser
from markupsafe import Markup
from slugify import slugify

from . import utilities


def register_on(app):
    @app.template_filter('strftime')
    def format_date_time_string(date: str, fmt=None) -> str:
        date = date_parser.parse(date)
        native = date.replace(tzinfo=None)
        the_format = '%d.%m.%y <strong>%H:%M</strong>'
        return native.strftime(the_format)

    @app.template_filter('gender')
    def translate_gender(gender: Union[int, str], fmt=None) -> str:
        return utilities.GENDER_INT_TO_STRING[int(gender)]

    @app.template_filter('slugify')
    def translate_gender(string: str, fmt=None) -> str:
        return slugify(string)

    @app.template_filter('markdown')
    def render_markdown(text: str) -> Markup:
        if not text:
            return Markup('')
        md = markdown_lib.Markdown()
        # don't pass raw HTML through, so user content can't inject markup
        md.preprocessors.deregister('html_block')
        md.inlinePatterns.deregister('html')
        return Markup(md.convert(text))
