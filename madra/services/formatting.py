"""Safe Markdown rendering: raw HTML, images and unsafe URLs are disabled."""

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from markupsafe import Markup

_parser = (
    MarkdownIt("commonmark", {"html": False, "breaks": True, "maxNesting": 20})
    .enable("table")
    .disable("image")
    .use(dollarmath_plugin, allow_labels=False)
)


def render_content(value):
    # Rendered HTML is generated solely by the trusted parser, never user HTML.
    return Markup(_parser.render(str(value or "")))
