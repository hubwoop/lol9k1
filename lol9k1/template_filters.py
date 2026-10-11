from typing import Union

import markdown as markdown_lib
from dateutil import parser as date_parser
from markupsafe import Markup
from slugify import slugify

from . import utilities


def register_on(app):
    @app.template_filter('strftime')
    def format_date_time_string(date: str) -> str:
        return date_parser.parse(date).strftime('%d.%m.%y <strong>%H:%M</strong>')

    @app.template_filter('gender')
    def translate_gender(gender: Union[int, str]) -> str:
        return utilities.GENDER_INT_TO_STRING[int(gender)]

    @app.template_filter('slugify')
    def slugify_filter(string: str) -> str:
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
