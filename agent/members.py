"""Bounded composition of explicitly requested members from one literal passage."""
import re

from .normalize import clean, literal_span


def member_count(question, kind='text', operation='single'):
    if kind != 'text' or operation != 'single':
        return 0
    match = re.match(r'^\s*(?:what|which)\s+(?:(?:are|were)\s+(?:the\s+)?)?'
                     r'(two|three|four|[2-4])\s+(?!of\b)[A-Za-z]', question, re.I)
    if not match:
        return 0
    return {'two': 2, 'three': 3, 'four': 4}.get(match[1].casefold(), int(match[1]) if match[1].isdigit() else 0)


def join_members(values):
    return ', '.join(values[:-1]) + ' and ' + values[-1]


def literal_members(question, values, evidence, kind='text', operation='single'):
    count = member_count(question, kind, operation)
    if not count or not isinstance(values, list) or len(values) != count:
        return None
    if any(not isinstance(value, str) or not 0 < len(clean(value)) <= 140 for value in values):
        return None
    values = [clean(value) for value in values]
    if len(join_members(values)) > 350:
        return None
    text = clean(evidence)
    intervals = []
    for value in values:
        if not literal_span(value, text, kind):
            return None
        start = text.find(value)
        intervals.append((start, start + len(value)))
    # Reject duplicates, aliases by containment and overlapping selections.
    # We deliberately do not guess whether two different names are aliases.
    for i, value in enumerate(values):
        for j in range(i):
            other = values[j]
            if value.casefold() in other.casefold() or other.casefold() in value.casefold():
                return None
            if max(intervals[i][0], intervals[j][0]) < min(intervals[i][1], intervals[j][1]):
                return None
    return values
