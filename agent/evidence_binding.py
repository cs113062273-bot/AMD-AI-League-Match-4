"""Resolve a candidate to one actual parsed source record before verification."""
from .normalize import clean


def bind(candidate, pages):
    exact, legacy = [], []
    signals = candidate.signals
    located = 'locator' in signals
    for page in pages:
        if page.url != candidate.source or page.error:
            continue
        # Parsed pages are immutable during candidate verification. Keep this
        # lookup indexed for large pages and repeated candidate checks.
        index = getattr(page, '_binding_index', None)
        stamp = (id(page.passages), len(page.passages))
        if index is None or index[0] != stamp:
            facts = {}
            for passage in page.passages:
                facts.setdefault(clean(passage.text), []).append(passage)
            index = (stamp, facts)
            page._binding_index = index
        for fact in index[1].get(clean(candidate.evidence), ()):
            if located and fact.locator != signals['locator']:
                continue
            # Production candidates carry the actual locator and scope. For
            # older locatorless callers, missing metadata may be recovered
            # only when the remaining source identity is unambiguous.
            if (located or candidate.label) and fact.label != candidate.label:
                continue
            if (located or candidate.section) and fact.section != candidate.section:
                continue
            if any(key in signals and signals[key] != value for key, value in (
                    ('structure', fact.kind), ('qualifiers', fact.qualifiers), ('field_value', fact.value))):
                continue
            if fact.label == candidate.label and fact.section == candidate.section:
                exact.append((page, fact))
            else:
                legacy.append((page, fact))
    # Empty labels are also real identities (e.g. a whole table row, unlike
    # its labelled cells). Prefer a complete scope match before recovering
    # omitted legacy metadata, never the first same-text record.
    matches = exact or legacy
    if not matches:
        return None
    first_page, first_fact = matches[0]
    # Exact duplicate records in one page are harmless; differing scope,
    # qualifiers, locators or page instances are ambiguous.
    if any(page is not first_page or fact != first_fact for page, fact in matches[1:]):
        return None
    return first_page, first_fact
