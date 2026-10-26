"""Make omitted HTML paragraph boundaries explicit without rewriting source text.

This is a narrow repair for the stdlib/BeautifulSoup parser, not an HTML5
tree builder. It inserts only closing paragraph tags at block starts.
"""
from html.parser import HTMLParser
import re


BLOCK = frozenset(('address article aside blockquote details dialog dir div dl dt dd fieldset '
    'figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr li listing main menu nav '
    'ol p pre search section table ul').split())
VOID = frozenset('area base br col embed hr img input link meta param source track wbr'.split())
SCOPE = frozenset('applet button caption html table td th marquee object template'.split())
OPAQUE = frozenset('script style textarea title xmp iframe noembed noframes plaintext svg math'.split())


class ParagraphBoundaries(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.positions = {}
        self.lines = [0] + [m.end() for m in re.finditer('\n', text)]
        self.insertions = []
        self.opaque = ''
        self.opaque_depth = 0

    def pop_from(self, index):
        while len(self.stack) > index:
            tag = self.stack.pop()
            self.positions[tag].pop()
            if not self.positions[tag]:
                del self.positions[tag]

    def handle_starttag(self, tag, attrs):
        if self.opaque:
            if tag == self.opaque and tag in {'svg', 'math'}:
                self.opaque_depth += 1
            return
        if tag in BLOCK and self.positions.get('p'):
            paragraph = self.positions['p'][-1]
            barrier = max((self.positions[t][-1] for t in SCOPE if t in self.positions), default=-1)
            if paragraph > barrier:
                line, column = self.getpos()
                self.insertions.append(self.lines[line - 1] + column)
                self.pop_from(paragraph)
        if tag not in VOID:
            if len(self.stack) >= 2048:
                raise ValueError('HTML paragraph repair depth limit')
            self.positions.setdefault(tag, []).append(len(self.stack))
            self.stack.append(tag)
            if tag in OPAQUE:
                self.opaque = tag
                self.opaque_depth = 1

    def handle_endtag(self, tag):
        if self.opaque:
            if tag != self.opaque or tag == 'plaintext':
                return
            self.opaque_depth -= 1
            if self.opaque_depth:
                return
            self.opaque = ''
        if tag in self.positions:
            self.pop_from(self.positions[tag][-1])


def close_paragraphs(text):
    if not re.search(r'<p[\s/>]', text, re.I):
        return text, False
    parser = ParagraphBoundaries(text)
    parser.feed(text)
    parser.close()
    if not parser.insertions:
        return text, False
    pieces = []
    start = 0
    for offset in parser.insertions:
        pieces.extend((text[start:offset], '</p>'))
        start = offset
    pieces.append(text[start:])
    return ''.join(pieces), True
