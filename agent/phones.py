"""Complete literal phone spans; syntax checks do not establish number ownership."""
import ipaddress
import re

from .normalize import clean


PAREN = r'(?:\+\d{1,3}[ .-]?)?\(\d{1,4}\)[ .-]?\d{1,12}(?:[ .-]\d{1,4}){0,4}'
LEGACY = r'(?:\+\d{1,3}[ .-]?)?\d{1,4}(?:[ .-]\d{1,4}){1,5}'
PATTERN = r'(?<![\w+)])(?:' + PAREN + '|' + LEGACY + r'|\+?\d{7,15})(?:\s*(?:ext\.?|x)\s*\d+)?(?!\w)'


def complete(value, evidence):
    value, evidence = clean(value), clean(evidence)
    if not re.fullmatch(PATTERN, value, re.I):
        return False
    main = re.split(r'\s*(?:ext\.?|x)\s*\d+$', value, flags=re.I)[0]
    if not 7 <= len(re.sub(r'\D', '', main)) <= 15 or re.fullmatch(r'\d{4}-\d{2}-\d{2}', main):
        return False
    try:
        ipaddress.ip_address(main)
        return False
    except ValueError:
        pass
    # A later separate occurrence can license the same digits, but a suffix
    # of a longer telephone number cannot supply a complete phone answer.
    return any(match[0] == value for match in re.finditer(PATTERN, evidence, re.I))
