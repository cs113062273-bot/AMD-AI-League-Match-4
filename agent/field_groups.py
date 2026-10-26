"""Bounded HTML label/value groups, with one explicit name in each group."""
from bs4 import Comment, NavigableString

from .normalize import clean
from .qualifiers import key_name


def _children(node):
    # Extra loose text would make the two-column interpretation ambiguous.
    if any(isinstance(child, NavigableString) and not isinstance(child, Comment)
           and clean(child) for child in node.contents):
        return []
    return node.find_all(recursive=False, limit=13)


def named_groups(soup):
    count = 0
    for index, group in enumerate(soup.find_all('div', limit=3000)):
        if group.find_parent(['table', 'dl', 'pre']):
            continue
        rows = _children(group)
        if not 2 <= len(rows) <= 12 or any(row.name != 'div' for row in rows):
            continue
        fields = {}; keys = set()
        for row in rows:
            cells = _children(row)
            if (len(cells) != 2 or any(cell.name != 'span' for cell in cells)
                    or row.find(['div', 'p', 'table', 'ul', 'ol', 'li', 'dl', 'br', 'section', 'article',
                                 'input', 'select', 'button', 'form'])):
                break
            label = clean(cells[0].get_text(' ', strip=True)).rstrip(':').strip()
            value = clean(cells[1].get_text(' ', strip=True))
            key = key_name(label)
            if (not 0 < len(label) <= 70 or len(label.split()) > 6 or not label[0].isalpha()
                    or not 0 < len(value) <= 220 or not key or key in keys):
                break
            keys.add(key); fields[label] = value
        if len(fields) != len(rows):
            continue
        names = [value for label, value in fields.items() if key_name(label) in {'name', 'fullname'}]
        if len(names) != 1:
            continue
        context = ' | '.join(f'{label}: {value}' for label, value in fields.items())
        if len(context) > 1000:
            continue
        yield index, fields, names[0], context
        count += 1
        if count >= 80:
            return
