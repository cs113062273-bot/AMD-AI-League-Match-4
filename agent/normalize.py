import re
import unicodedata
from datetime import datetime
from calendar import month_name
from .number_atoms import scaled_runs

_GROUPED_NUMBER=re.compile(r'(?<![\d.,])[-+\u2212]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?!\d|,\d)')


def clean(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(text))).strip()


def normalize(value, kind="text", precision=''):
    value = clean(value)
    if kind=='date' and precision=='month':
        month=iso_month(value)
        if month:return month_name[int(month[5:7])]+' '+month[:4]
    if kind == "version":
        value = re.sub(r"^[vV](?=\d)", "", value)
    # Preserve punctuation, units, currencies and phone country codes: Match 4 comparison is unknown.
    return value


def equivalence(value):
    return clean(value).casefold()


def calendar_years(text):
    # Standards identifiers are not calendar dates.
    text=re.sub(r'\b(?:PEP|RFC)\s*[- :/#]*\d+\b','',text,flags=re.I)
    return [year for year in re.findall(r'(?<![\w.])\d{4}(?!\w|\.\w)',text) if int(year)>0]


def literal_span(value, evidence, kind="text"):
    """Exact normalized span with identifier/number boundaries; 4.3 is not proof of 4.30."""
    value, evidence = clean(value), clean(evidence)
    if not value:
        return False
    def word(char):
        return char.isascii() and (char.isalnum() or char == "_")
    numeric=kind in {'number','percentage','measurement','duration','price','year','time'}
    grouped=[m.span() for m in _GROUPED_NUMBER.finditer(evidence)] if numeric and ',' in evidence else []
    scaled=list(scaled_runs(evidence)) if numeric else []
    start=0
    while True:
        pos=evidence.find(value,start)
        if pos<0:return False
        end=pos+len(value)
        left=evidence[pos-1] if pos else ""
        right=evidence[end] if end<len(evidence) else ""
        bad_left=bool(left and value[0].isalnum() and (word(left) or left=="." and pos>=2 and word(evidence[pos-2])))
        if value[0] in '+-−' and len(value)>1 and value[1].isdigit() and left and word(left):bad_left=True
        if numeric and value[0].isdigit():
            if left in {'-','+','−','＋'} or left in {'/',':'} and pos>=2 and evidence[pos-2].isdigit():bad_left=True
        # A substring of a grouped scalar is not the supplied numeric value.
        # Keep searching: a later standalone occurrence can still support it.
        if any(a<pos<b for a,b in grouped):bad_left=True
        if any(a<pos<b for a,b in scaled):bad_left=True
        if kind=="version" and left in "vV" and left and (pos<2 or not word(evidence[pos-2])):
            bad_left=False
        bad_right=bool(right and value[-1].isalnum() and (word(right) or right=="." and end+1<len(evidence) and word(evidence[end+1])))
        if any(a<end<b for a,b in grouped):bad_right=True
        if any(a<end<b for a,b in scaled):bad_right=True
        if kind=='time' and (right==':' or re.match(r'\s*[ap]\.?m\b',evidence[end:],re.I)):bad_right=True
        if kind=="date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}",value) and re.match(r"T\d{2}:\d{2}",evidence[end:]):
            bad_right=False
        if kind=='date' and re.fullmatch(r'\d{4}-\d{2}',value) and re.match(r'[-/.]\d',evidence[end:]):bad_right=True
        if kind=="version" and re.match(r"[-.]?(?:alpha|beta|rc|dev|pre)\d*",evidence[end:],re.I):
            bad_right=True
        if not bad_left and not bad_right:return True
        start=pos+1


def iso_date(value):
    s = clean(value)
    numeric=re.fullmatch(r'(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})',s) or re.fullmatch(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日?',s)
    if numeric:
        try:return datetime(*map(int,numeric.groups())).date().isoformat()
        except ValueError:return ''
    numeric=re.fullmatch(r'(\d{1,2})([/.\-])(\d{1,2})\2(\d{4})',s)
    if numeric:
        first,second,year=int(numeric[1]),int(numeric[3]),int(numeric[4])
        if first<=12 and second<=12 and first!=second:return ''
        month,day=(second,first) if first>12 or first==second else (first,second)
        try:return datetime(year,month,day).date().isoformat()
        except ValueError:return ''
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", s)
    if match:
        try:
            return datetime.strptime(match[0], "%Y-%m-%d").date().isoformat()
        except ValueError:
            return ""
    s = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", s)
    for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y", "%d %b %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""  # Ambiguous numeric locale dates intentionally stay ambiguous.


def iso_month(value):
    """Project a valid literal calendar date; never infer a missing year/month."""
    date=iso_date(value)
    if date:return date[:7]
    value=clean(value)
    for fmt in ('%B %Y','%b %Y','%Y-%m'):
        try:return datetime.strptime(value,fmt).strftime('%Y-%m')
        except ValueError:continue
    return ''
