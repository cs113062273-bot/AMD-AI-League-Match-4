"""Structure-preserving extraction; fetched content is data, never executable instructions."""
from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from pypdf.errors import PyPdfError

from bs4 import BeautifulSoup,Comment,NavigableString

from .network import Response
from .normalize import clean,literal_span
from .types import Page, Passage
from .urls import canonical_url,discovery_url
from .qualifiers import record_qualifiers
from .challenges import interstitial
from .field_groups import named_groups
from .html_paragraphs import close_paragraphs, BLOCK


def prefix(text, limit):
    """Clip at a word boundary so a cut decimal/version can never become evidence."""
    if len(text) <= limit:
        return text
    if text[limit].isspace() or text[limit-1].isspace():
        return text[:limit].rstrip()
    end = text.rfind(' ',0,limit)
    return text[:end] if end >= 0 else ''


def first_source_line(el):
    """An actual preformatted line or BR boundary, never an inline-tag boundary."""
    if el.name=='pre':
        lines=el.get_text().splitlines()
        first=clean(lines[0]) if lines else ''
    elif el.find('br'):
        pieces=[]
        for node in el.descendants:
            if getattr(node,'name',None)=='br':break
            if isinstance(node,NavigableString) and not isinstance(node,Comment):pieces.append(str(node))
        first=clean(''.join(pieces))
    else:return ''
    return first if 0<len(first)<=350 else ''


def inline_field(el):
    """A leading, explicitly marked label: value in one paragraph."""
    if el.name != 'p':return None
    nodes=[node for node in el.contents if not isinstance(node,Comment) and
           (getattr(node,'name',None) or clean(str(node)))]
    if not nodes or getattr(nodes[0],'name',None) not in {'span','b','strong'}:return None
    marked=clean(nodes[0].get_text(' ',strip=True))
    if not marked.endswith(':') or not 1<=len(marked)<=80 or len(marked.split())>6:return None
    label=marked[:-1].strip()
    text=clean(el.get_text(' ',strip=True))
    if not label or not text.startswith(marked):return None
    if el.find('br') or any(clean(node.get_text(' ',strip=True)).endswith(':')
            for node in el.find_all(['span','b','strong']) if node is not nodes[0]):return None
    value=text[len(marked):].strip()
    if not 0<len(value)<=350:return None
    return text,label,value


def segments(text, width=1600, overlap=200):
    offset=0
    while offset<len(text):
        part=prefix(text[offset:],width)
        if part:
            yield offset,part
            end=offset+len(part)
            if end>=len(text):break
            start=text.find(' ',max(offset+1,end-overlap),end)
            offset=start+1 if start>=0 else end+1
        else:
            end=text.find(' ',offset+width)
            if end<0:break
            offset=end+1


def _flatten(obj, page, path="", depth=0, parent="", qualifiers=None):
    if depth > 16 or len(path)>512 or len(page.passages) >= 3500:
        page.truncated=True
        return
    if isinstance(obj, dict):
        if len(obj)>200:page.truncated=True
        fields={k:_scalar(v) for k,v in list(obj.items())[:200] if len(k)<=120 and not isinstance(v,(dict,list)) and len(str(v))<220}
        local=" | ".join(f"{key}: {value}" for key,value in fields.items())
        context=(f'{path or "$"} {{ {local} }}'+(' | parent '+parent if parent else '')) if local else parent
        if len(context)>1800:page.truncated=True
        context=prefix(context,1800)
        qualified=record_qualifiers(fields,qualifiers,path)
        schema = obj.get('@type')
        if isinstance(schema,str):qualified['schema_types']=[schema.rsplit('/',1)[-1]]
        elif isinstance(schema,list):qualified['schema_types']=[s.rsplit('/',1)[-1] for s in schema if isinstance(s,str)][:8]
        for k, v in list(obj.items())[:200]:
            _flatten(v, page, f"{path}.{k}".strip("."), depth+1,context,qualified)
    elif isinstance(obj, list):
        if len(obj)>300:page.truncated=True
        for i, v in enumerate(obj[:300]):
            _flatten(v, page, f"{path}[{i}]", depth+1, parent,qualifiers)
    else:
        if len(clean(_scalar(obj)))>1800:page.truncated=True
        value = prefix(clean(_scalar(obj)),1800)
        label = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
        label = label.replace("_", " ")
        page.passages.append(Passage(f"{label}: {value}" + (f" | {parent}" if parent else ""),
            label, value, parent[:400], "json", path,
            {**(qualifiers or {}),'value_type':'boolean' if type(obj) is bool else 'null' if obj is None else 'scalar',
             **({'source_continues':True} if len(value)<len(clean(_scalar(obj))) else {})}))


def _scalar(value):
    if value is None:return 'null'
    if type(value) is bool:return 'true' if value else 'false'
    return str(value)


def _json(text):
    # Preserve numeric spelling (1.00, 1e-6) rather than fabricating a normalized span.
    return json.loads(text.lstrip('\ufeff'),parse_int=str,parse_float=str,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-JSON numeric constant')))


def _table(table, section, page, idx):
    grid, occupied = [], {}
    rows=table.find_all('tr')
    if len(rows)>1500:page.truncated=True
    for r, row in enumerate(rows[:1500]):
        if row.find_parent("table") is not table:
            continue
        vals, col = [], 0
        cells=row.find_all(['th','td'],recursive=False)
        if len(cells)>100:page.truncated=True
        for cell in cells[:100]:
            if col >= 100:
                page.truncated=True
                break
            while col<100 and (r, col) in occupied:
                vals.append(occupied[r, col]); col += 1
            text = prefix(clean(cell.get_text(" ", strip=True)),1800)
            try:
                rs, cs = int(cell.get("rowspan", 1)), int(cell.get("colspan", 1))
            except ValueError:
                rs, cs = 1, 1
            if rs==0 or rs>100 or cs>50:
                page.truncated=True
                return  # Do not fabricate column associations by clamping a large span.
            for j in range(max(1, cs)):
                if col+j>=100:page.truncated=True;break
                vals.append(text)
                for k in range(1, max(1, rs)):
                    occupied[r+k, col+j] = text
            col += max(1, cs)
        while col<100 and (r, col) in occupied:
            vals.append(occupied[r, col]); col += 1
        if vals:
            grid.append(vals)
        occupied = {key: value for key, value in occupied.items() if key[0] > r}
    if not grid:
        return
    has_header = bool(table.find("tr") and table.find("tr").find("th"))
    headers = grid[0] if has_header else []
    caption=table.find('caption',recursive=False)
    caption=clean(caption.get_text(' ',strip=True)) if caption else ''
    for r, vals in enumerate(grid[1:] if has_header else grid):
        if len(page.passages)>=3500:break
        row_context = prefix(" | ".join(f"{headers[c] + ': ' if c < len(headers) else ''}{v}" for c, v in enumerate(vals)),6000)
        row_facts={'table':idx,'row':r,'columns':headers,'cells':vals}
        if caption:row_facts.update(table_caption=caption[:1100],caption_continues=len(caption)>1100)
        page.passages.append(Passage(row_context, section=section, kind="table", locator=f"table[{idx}]/row[{r}]",qualifiers=row_facts))
        if len(vals) == 2 and not headers:
            page.passages.append(Passage(row_context, vals[0], vals[1], section, "field", f"table[{idx}]/row[{r}]/1"))
        else:
            for c, val in enumerate(vals):
                if len(page.passages)>=3500:break
                label = headers[c] if c < len(headers) else ""
                if label and val:
                    evidence=row_context if f'{label}: {val}' in row_context else f'{label}: {val} | '+row_context
                    page.passages.append(Passage(evidence, label, val, section, "cell", f"table[{idx}]/row[{r}]/cell[{c}]",
                        {**row_facts,'column':c}))


def parse_response(resp: Response):
    page = Page(resp.url, redirects=resp.redirects, status=resp.status, error=resp.error,truncated=resp.truncated)
    if resp.error or not resp.body:
        return page
    ct = resp.content_type.casefold()
    text = resp.text
    try:
        if resp.body.startswith(b"%PDF") or "application/pdf" in ct:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(resp.body))
            if len(reader.pages)>30:page.truncated=True
            for i, pdfpage in enumerate(reader.pages[:30]):
                for part in (pdfpage.extract_text() or "").splitlines():
                    part = clean(part)
                    if part:
                        for offset,span in segments(part,width=2000):
                            if len(page.passages)>=3500:return page
                            page.passages.append(Passage(span, section=f"PDF page {i+1}", locator=f"page[{i+1}]:{offset}"))
            return page
        if "json" in ct or text.lstrip().startswith(("{", "[")):
            from .familysearch import published_key,parse_published
            family_id=published_key(resp.url)
            if family_id:return parse_published(resp,family_id)
            _flatten(_json(text), page)
            return page
        if "csv" in ct or url_path(resp.url).endswith(".csv"):
            from itertools import islice
            original=list(islice(csv.reader(io.StringIO(text)),1501))
            if len(original)>1500 or any(len(row)>100 or any(len(value)>1800 for value in row) for row in original):page.truncated=True
            rows = [[prefix(clean(value),1800) for value in row[:100]] for row in original[:1500]]
            if rows:
                for r, row in enumerate(rows[1:]):
                    ctx = prefix(" | ".join(f"{k}: {v}" for k, v in zip(rows[0], row)),6000)
                    for k, v in zip(rows[0], row):
                        if len(page.passages)>=3500:return page
                        evidence=ctx if f'{k}: {v}' in ctx else f'{k}: {v} | '+ctx
                        page.passages.append(Passage(evidence, k, v, kind="cell", locator=f"row[{r}]"))
            return page
        if "xml" in ct or text.lstrip().startswith("<?xml"):
            root = ET.fromstring(text)
            parents={child:parent for parent in root.iter() for child in parent}
            for i, el in enumerate(root.iter()):
                if i >= 3500:
                    page.truncated=True
                    break
                if el.text and el.text.strip():
                    label = el.tag.rsplit("}", 1)[-1]
                    value = clean(el.text)
                    parent=parents.get(el)
                    context=prefix(' | '.join(child.tag.rsplit('}',1)[-1]+': '+clean(child.text)
                        for child in list(parent)[:100] if child.text and child.text.strip() and len(child.text)<220),1800) if parent is not None else ''
                    attributes=prefix(' '.join(f'{k}={v}' for k,v in list(el.attrib.items())[:20]),350)
                    for offset,span in segments(value,width=1800):
                        if len(page.passages)>=3500:return page
                        evidence=f'{label}: {span}'+(' | '+context if context else '')
                        page.passages.append(Passage(evidence,label,span,attributes,'xml',f'{i}:{offset}'))
            return page
        if "html" not in ct and not re.search(r"<(?:html|body|head|div|p|h1|table|dl)\b", text, re.I):
            lines=text.splitlines()
            if len(lines)>3500:page.truncated=True
            for i, line in enumerate(lines[:3500]):
                if clean(line):
                    for offset,span in segments(clean(line),width=2000):
                        if len(page.passages)>=3500:return page
                        page.passages.append(Passage(span, locator=f"line[{i}]:{offset}",
                            qualifiers={'source_line':i+1,'complete_line':offset==0 and len(clean(line))<=2000,
                                **({'source_continues':True} if offset+len(span)<len(clean(line)) else {})}))
            return page
        paragraph_text, repaired_paragraphs = close_paragraphs(text)
        soup = BeautifulSoup(paragraph_text, "html.parser")
        active_scripts=[script for script in soup.find_all('script')[:100] if script.get('type','') not in {'application/json','application/ld+json'}]
        page.dynamic = bool(active_scripts) and len(clean(soup.get_text(' ',strip=True)))<250
        page.title = prefix(clean(soup.title.get_text(" ")),500) if soup.title else ""
        challenge = interstitial(soup, resp.status)
        if challenge:
            page.error = 'challenge_' + challenge
            page.dynamic = False
            return page
        canon = soup.find("link", rel="canonical")
        if canon:
            page.canonical = canonical_url(canon.get("href", ""), resp.url)
        if re.search(r"^(?:404|page not found|not found|access denied|just a moment)", page.title, re.I):
            page.error = "soft_error_page"
            return page
        for i, script in enumerate(soup.find_all("script")[:100]):
            if script.get("type") in {"application/ld+json", "application/json"}:
                try:
                    start = len(page.passages)
                    _flatten(_json(script.string or script.get_text()), page, "")
                    for p in page.passages[start:]:
                        p.kind = "jsonld" if script.get("type") == "application/ld+json" else "embedded"
                        p.locator = f"script[{i}]/" + p.locator
                except (ValueError, RecursionError, TypeError):
                    continue
        meta_counts={}
        for mi,meta in enumerate(soup.find_all("meta")[:150]):
            key = meta.get("name") or meta.get("property") or meta.get("itemprop")
            value = clean(meta.get("content", ""))
            if key and value:
                meta_counts[key]=meta_counts.get(key,0)+1
                section=f'{key} metadata entry {meta_counts[key]}' if str(key).casefold() in {'citation_author','dc.creator'} else ''
                page.passages.append(Passage(f"{key}: {value}", key, value,section,'meta',f'meta[{mi}]'))
        for el in soup.select("script,style,noscript,nav,footer,aside,form,[hidden],[aria-hidden='true']"):
            el.decompose()
        for el in soup.find_all(style=True):
            if el.decomposed:continue
            if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", el.get("style", ""), re.I):
                el.decompose()
        # No-script notices and hidden compatibility banners are not rendered
        # article content. They can make an empty JS application look static.
        # Only promote truly empty bodies; short readable pages keep their
        # existing classification and embedded source data remains available.
        if active_scripts and not page.truncated and soup.body and not clean(soup.body.get_text(' ',strip=True)):
            if not any(p.kind in {'jsonld','embedded'} for p in page.passages):
                page.dynamic = True
        for a in soup.find_all("a", href=True)[:2500]:
            href, label = str(a["href"]), clean(a.get_text(" ", strip=True))
            definition=a.find_parent('dd')
            term=definition.find_previous_sibling('dt') if definition else None
            if term:
                name=clean(term.get_text(' ',strip=True))
                if len(name)<=80 and '(' not in name:label=name+' '+label
            if href.startswith(("tel:", "mailto:")):
                kind = "phone" if href.startswith("tel:") else "email"
                value = href.split(":", 1)[1].split("?", 1)[0]
                context = clean(a.parent.get_text(" ", strip=True))[:600]
                page.passages.append(Passage(context + " | " + value, kind + " " + context, value, kind="field"))
            else:
                link = canonical_url(href, resp.url)
                if link and link != resp.url:
                    page.links.append((link, label[:250]))
        for author_group in soup.select(".authors")[:5]:
            context = clean(author_group.get_text(" ", strip=True))
            for ai, author in enumerate(author_group.find_all("a")[:50]):
                name = clean(author.get_text(" ", strip=True))
                if name:
                    page.passages.append(Passage(context, "first author" if ai == 0 else "author", name,
                        "Authors", "field", f"authors[{ai}]"))
        if not page.truncated:
            for gi, fields, name, context in named_groups(soup):
                if len(page.passages)+len(fields)>3500:
                    page.truncated=True
                    break
                qualifiers={**record_qualifiers(fields),'identity':[name],'named_field_group':True}
                for fi,(label,value) in enumerate(fields.items()):
                    page.passages.append(Passage(context,label,value,page.title,'field',f'fieldgroup[{gi}]/{fi}',qualifiers))
        record_nodes=soup.select('h1,h2,h3,h4,h5,h6,article,[role="row"]')
        compact_records={};record_count=0
        for el in record_nodes:
            if el.name in {'h1','h2','h3','h4','h5','h6'}:continue
            if record_count>=1500:break
            record_count+=1
            # Leave existing heading/prose, table and API-signature extraction
            # intact. Compact records cover otherwise unlabelled row layouts.
            if el.find(['article','table','pre','dl','h1','h2','h3','h4','h5','h6']):continue
            children=el.find_all(recursive=False,limit=13)
            if not 2<=len(children)<=12:continue
            values=[clean(child.get_text(' ',strip=True)) for child in children]
            value=' | '.join(part for part in values if part)
            if sum(bool(part) for part in values)>=2 and 10<=len(value)<=800:
                compact_records[id(el)]=value
        section = ""
        for i, el in enumerate(soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "dt", "table", "pre", "address", "blockquote"])):
            if len(page.passages) >= 3500:
                break
            if id(el) in compact_records or any(id(parent) in compact_records for parent in el.parents):
                continue
            if el.name.startswith("h"):
                section = prefix(clean(el.get_text(" ", strip=True)),350)
                page.passages.append(Passage(section, section=section, kind="heading", locator=f"heading[{i}]"))
                if el.name == "h1":
                    title_value = re.sub(r"^(?:PEP\s+\d+\s*[–—-]\s*|Title:\s*)", "", section)
                    page.passages.append(Passage(section, "title", title_value, section, "field", f"h1[{i}]"))
            elif el.name == "table":
                _table(el, section, page, i)
            elif el.find_parent(["table", "li", "pre", "blockquote"]):
                continue
            elif el.name == "dt":
                if "sig" in (el.get("class") or []):
                    signature = clean(el.get_text(" ", strip=True))
                    page.passages.append(Passage(signature, section=section, kind="signature", locator=f"signature[{i}]"))
                dd = el.find_next_sibling("dd")
                if dd:
                    label, value = clean(el.get_text(" ")), clean(dd.get_text(" "))
                    page.passages.append(Passage(f"{label}: {value}", label, value, section, "field", f"dl[{i}]"))
            else:
                value = clean(el.get_text(" ", strip=True))
                if value:
                    field=inline_field(el)
                    if field:
                        evidence,label,field_value=field
                        page.passages.append(Passage(evidence,label,field_value,section,'field',f'inline[{i}]'))
                    if section.casefold() in {'default','default value','default setting'} and len(value)<=120:
                        page.passages.append(Passage(value,section,value,section,'field',f'default[{i}]'))
                    if el.get("class") and "authors" in el.get("class", []):
                        authors = el.find_all("a")
                        for ai, author in enumerate(authors[:50]):
                            name = clean(author.get_text(" ", strip=True))
                            page.passages.append(Passage(value, "first author" if ai == 0 else "author", name,
                                section, "field", f"authors[{ai}]"))
                    for offset,span in segments(value):
                        if len(page.passages)>=3500:break
                        page.passages.append(Passage(span, section=section, locator=f"{el.name}[{i}]:{offset}",
                            qualifiers={'source_continues':True} if offset+len(span)<len(value) else {}))
        # Compact semantic records often use div columns inside an article/ARIA
        # row rather than a table. Keep the name and value in the same record.
        record_headings=[];record_banner=[];seen_h1=False
        for i,el in enumerate(record_nodes):
            if el.name in {'h1','h2','h3','h4','h5','h6'}:
                level=int(el.name[1])
                if level==1 and not seen_h1:
                    # Some layouts put a category h2 before the page h1.
                    # Retain that banner, then replace normal sibling scopes.
                    record_banner=[text for depth,text in record_headings][-3:]
                    seen_h1=True
                record_headings=[entry for entry in record_headings if entry[0]<level]
                record_headings.append((level,prefix(clean(el.get_text(' ',strip=True)),350)))
                continue
            if len(page.passages)>=3500:break
            value=compact_records.get(id(el))
            if value:
                section=prefix(' > '.join(record_banner+[text for level,text in record_headings]),700) or page.title
                source_fields={key[5:]:clean(raw) for key,raw in list(el.attrs.items())[:24]
                    if key.startswith('data-') and len(key)<=65 and isinstance(raw,str) and 0<len(clean(raw))<=120
                    and literal_span(clean(raw),value)}
                page.passages.append(Passage(value,section=section,kind='record',locator=f'record[{i}]',
                    qualifiers={'source_fields':source_fields} if source_fields else {}))
        # Many sites use div/span-only specification layouts. Extract leaf blocks without duplicating the whole DOM.
        existing = {p.text for p in page.passages}
        for i, el in enumerate(soup.find_all(["div", "span"])[:5000]):
            if len(page.passages) >= 3500:
                break
            if id(el) in compact_records or el.find_parent(['table','li','pre','blockquote','p']) or any(id(parent) in compact_records for parent in el.parents):
                continue
            if el.find(["div", "p", "table", "li", "dl"]):
                continue
            value = clean(el.get_text(" ", strip=True))
            if 3 <= len(value) <= 1000 and value not in existing:
                page.passages.append(Passage(value, locator=f"block[{i}]"))
                existing.add(value)
        # ARIA and microdata fields, including values supplied via content attributes.
        visible=[p for p in page.passages if p.kind not in {'meta','heading','jsonld','embedded'} and p.label!='title']
        if not visible:
            # Legacy pages can put readable facts directly in body/bold/br nodes.
            body=clean((soup.body or soup).get_text(' ',strip=True))
            for offset,span in segments(body):
                if len(page.passages)>=3500:break
                if span:page.passages.append(Passage(span,section=page.title,locator=f'body:{offset}',
                    qualifiers={'source_continues':True} if offset+len(span)<len(body) else {}))
        for el in soup.find_all(attrs={"itemprop": True})[:300]:
            value = clean(el.get("content") or el.get_text(" ", strip=True))
            if value:
                page.passages.append(Passage(f"{el['itemprop']}: {value}", el["itemprop"], value, kind="field"))
        # Preserve explicit line structure for first-line requests. Add these
        # after normal extraction so they do not displace ordinary page facts.
        line_count=0
        for i,el in enumerate(soup.find_all(['p','pre','div','blockquote'],limit=3000)):
            if len(page.passages)>=3500 or line_count>=200:break
            if el.find(['p','pre','div','table','li','dl','blockquote']):continue
            first=first_source_line(el)
            if not first:continue
            heading=el.find_previous(['h1','h2','h3','h4','h5','h6'])
            section=prefix(clean(heading.get_text(' ',strip=True)),350) if heading else page.title
            page.passages.append(Passage(first,'line 1','',section,'line',f'lines[{i}]/line[0]',
                {'source_line':1,'complete_line':True}))
            line_count+=1
        if repaired_paragraphs:
            # Repairing optional end tags separates formerly nested paragraphs.
            # Retain bounded adjacent context, not the old whole-page suffix.
            for i, el in enumerate(soup.find_all('p', limit=1500)):
                if len(page.passages) >= 3500:break
                if el.find_parent(['table','li','pre','blockquote','p']) or el.find(list(BLOCK)):continue
                texts=[clean(el.get_text(' ',strip=True))]
                if not texts[0] or len(texts[0])>1100:continue
                for sibling in el.next_siblings:
                    if isinstance(sibling,Comment):continue
                    if isinstance(sibling,NavigableString):
                        if clean(str(sibling)):break
                        continue
                    if sibling.name!='p' or sibling.find(list(BLOCK)):break
                    value=clean(sibling.get_text(' ',strip=True))
                    if not value:break
                    if len(' '.join([*texts,value]))>1100:break
                    texts.append(value)
                    if len(texts)==3:break
                if len(texts)>1:
                    heading=el.find_previous(['h1','h2','h3','h4','h5','h6'])
                    section=prefix(clean(heading.get_text(' ',strip=True)),350) if heading else ''
                    page.passages.append(Passage(' '.join(texts),section=section,
                        locator=f'paragraphs[{i}]+{len(texts)}',
                        qualifiers={'paragraph_window':True,'paragraph_count':len(texts)}))
        dedup = {}
        if len(page.passages)>=3500:page.truncated=True
        for p in page.passages:
            # Identical words under another heading can describe a different
            # entity/year. Keep that scope available to the evidence reader.
            key = (p.text, p.label, p.value, p.section)
            if key not in dedup:
                dedup[key] = p
        page.passages = list(dedup.values())[:3500]
        page.links = list(dict.fromkeys(page.links))[:1500]
    except (ValueError, TypeError, RecursionError, ET.ParseError, OSError, PyPdfError,csv.Error) as exc:
        page.error = f"parse_{type(exc).__name__}"
    finally:
        if discovery_url(page.url):page.passages=[]
        if len(page.passages)>=3500:page.truncated=True
    return page


def url_path(url):
    from urllib.parse import urlsplit
    return urlsplit(url).path.casefold()
