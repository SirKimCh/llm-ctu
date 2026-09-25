from html.parser import HTMLParser

SKIPPED = {"script", "style", "noscript", "nav", "aside", "form", "iframe", "svg", "template", "button", "select", "head", "title"}
CHROME = {"header", "footer"}
CONTENT = {"article", "main"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCKS = {"p", "div", "section", "li", "ul", "ol", "br", "blockquote", "dd", "dt", "pre", "hr", "figcaption", *HEADINGS, *CONTENT}
CELLS = {"td", "th"}


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skipping = 0
        self.content_depth = 0
        self.page_lines: list[str] = []
        self.content_lines: list[str] = []
        self.inline: list[str] = []
        self.heading = False
        self.rows: list[list[str]] | None = None
        self.cells: list[str] | None = None

    def _ignored(self, tag: str) -> bool:
        return tag in SKIPPED or (tag in CHROME and not self.content_depth)

    def handle_starttag(self, tag, attrs):
        if self._ignored(tag):
            self.skipping += 1
        if self.skipping:
            return
        if tag == "table" and self.rows is None:
            self._flush()
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.cells = []
        elif tag in CELLS and self.cells is not None:
            self.inline = []
        elif tag in BLOCKS and self.cells is not None:
            self.inline.append(" ")
        elif tag in BLOCKS:
            self._flush()
            self.heading = tag in HEADINGS
        if tag in CONTENT:
            self.content_depth += 1

    def handle_endtag(self, tag):
        if self._ignored(tag) and self.skipping:
            self.skipping -= 1
            return
        if self.skipping:
            return
        if tag in CELLS and self.cells is not None:
            self.cells.append(self._text().replace("|", "/"))
            self.inline = []
        elif tag == "tr" and self.cells is not None:
            if any(self.cells):
                self.rows.append(self.cells)
            self.cells = None
        elif tag == "table" and self.rows is not None:
            self._emit_table(self.rows)
            self.rows = None
        elif tag in BLOCKS:
            self._flush()
        if tag in CONTENT:
            self.content_depth -= 1

    def handle_data(self, data):
        if not self.skipping:
            self.inline.append(data)

    def _text(self) -> str:
        return " ".join("".join(self.inline).split())

    def _add(self, line: str) -> None:
        self.page_lines.append(line)
        if self.content_depth:
            self.content_lines.append(line)

    def _flush(self) -> None:
        if self.cells is not None:
            return
        text = self._text()
        self.inline = []
        if text:
            self._add(f"# {text}" if self.heading else text)
        self.heading = False

    def _emit_table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        width = max(len(row) for row in rows)
        lines = [f"| {' | '.join(row + [''] * (width - len(row)))} |" for row in rows]
        self._add("\n".join([lines[0], f"|{' --- |' * width}", *lines[1:]]))


def html_to_markdown(html: str) -> str:
    """Văn bản của trang: ưu tiên <article>/<main>; bỏ menu, script, header/footer ngoài nội dung; bảng dựng từ <tr>/<td>."""
    parser = _PageText()
    parser.feed(html)
    parser.close()
    parser._flush()
    return "\n\n".join(parser.content_lines or parser.page_lines)
