"""Read a discovered Oyez case through its keyless official JSON endpoint."""
import json
import re
from dataclasses import replace
from urllib.parse import urlsplit

from .network import Response
from .normalize import clean, literal_span
from .parser import parse_response, segments
from .types import Page, Passage


def case_key(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password
                or parsed.hostname not in {'oyez.org', 'www.oyez.org', 'api.oyez.org'}
                or parsed.port not in {None, 443 if parsed.scheme == 'https' else 80}):
            return None
        match = re.fullmatch(r'/cases/(\d{4})/([0-9][A-Za-z0-9_-]{0,63})/?', parsed.path, re.ASCII)
        return match.groups() if match else None
    except (ValueError, TypeError):
        return None


def parse_case(response, key):
    """Identity is checked before any body field can become answer evidence."""
    page = Page(response.url, status=response.status, redirects=response.redirects,
                truncated=response.truncated)
    if response.error or response.status != 200 or response.truncated:
        page.error = response.error or 'oyez_incomplete_response'
        return page
    if case_key(response.url) != key or urlsplit(response.url).hostname != 'api.oyez.org':
        page.error = 'oyez_response_identity_mismatch'
        return page
    try:
        data = json.loads(response.text)
    except (ValueError, RecursionError):
        data = None
    if (not isinstance(data, dict) or str(data.get('term', '')) != key[0]
            or str(data.get('docket_number', '')) != key[1]
            or not isinstance(data.get('href'), str) or case_key(data['href']) != key
            or urlsplit(data['href']).hostname != 'api.oyez.org'
            or not isinstance(data.get('name'), str) or not 0 < len(clean(data['name'])) <= 500):
        page.error = 'oyez_case_identity_mismatch'
        return page
    page.title = clean(data['name'])
    page.identity = {'registry': 'oyez', 'term': key[0], 'docket': key[1]}
    page.canonical = f'https://www.oyez.org/cases/{key[0]}/{key[1]}'
    page.links.append((page.canonical, page.title))
    for field in ('facts_of_the_case', 'question', 'conclusion', 'description'):
        html = data.get(field)
        if not isinstance(html, str) or not html.strip():
            continue
        if len(html) > 120_000:
            page.truncated = True
            continue
        # This HTML is a fetched JSON field, not a separately fetched page.
        # Reuse the ordinary hidden/script filtering and block boundaries.
        fragment = parse_response(Response(response.url, body=html.encode('utf-8'),
                                  content_type='text/html', status=200))
        for passage in fragment.passages:
            if passage.kind not in {'prose', 'heading', 'cell', 'table', 'record'}:
                continue
            for offset, text in segments(passage.text, width=1000, overlap=150):
                if len(page.passages) >= 96:
                    page.truncated = True
                    return page
                page.passages.append(replace(passage, text=text,
                    section=field.replace('_', ' ') + (' > ' + passage.section if passage.section else ''),
                    locator=f'oyez/{field}/{passage.locator}:{offset}'))
    for field in ('first_party', 'second_party', 'docket_number', 'term'):
        if len(page.passages) >= 96:
            page.truncated = True
            break
        value = data.get(field)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and 0 < len(str(value)) <= 500:
            label = field.replace('_', ' ')
            page.passages.append(Passage(f'{label}: {value}', label=label, value=str(value),
                kind='field', locator='oyez/' + field))
    if not page.passages:
        page.error = 'oyez_no_case_content'
    return page


async def adapt_case(requested_url, response, fetcher):
    key = case_key(requested_url)
    if key is None:
        return None
    if urlsplit(requested_url).hostname != 'api.oyez.org':
        response = await fetcher.fetch(f'https://api.oyez.org/cases/{key[0]}/{key[1]}?labels=true')
    return parse_case(response, key)


def rendered_case_supported(api_page, rendered):
    """A frontend citation requires an actual rendered case, not an API relabel."""
    key = (api_page.identity.get('term'), api_page.identity.get('docket'))
    if (api_page.error or api_page.truncated or api_page.identity.get('registry') != 'oyez' or not rendered
            or rendered.error or rendered.truncated or case_key(rendered.url) != key
            or urlsplit(rendered.url).hostname not in {'www.oyez.org', 'oyez.org'}):
        return False
    titles = [rendered.title.removesuffix(' | Oyez')]
    titles.extend(p.value for p in rendered.passages if p.label == 'og:title')
    if clean(api_page.title) not in {clean(title) for title in titles}:
        return False
    # Require a substantial visible case-content block, not matching metadata,
    # a bare title or a link back to the API. The DOM remains the cited evidence.
    facts = [p for p in api_page.passages if p.kind == 'prose'
             and p.section.split(' > ', 1)[0] in {'facts of the case', 'question', 'conclusion'}]
    return (any(len(fact.text) >= 80 for fact in facts)
        and all(any(literal_span(fact.text, visible.text)
                    for visible in rendered.passages if visible.kind == 'prose') for fact in facts))


def unrendered_passages(api_page, rendered):
    """Keep API-only fields available without duplicating rendered case prose."""
    return [fact for fact in api_page.passages if not (fact.kind == 'prose'
        and any(literal_span(fact.text, visible.text) for visible in rendered.passages if visible.kind == 'prose'))]
