from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import math
import os
import re
import time
import traceback
from urllib.parse import urlsplit

from .types import Settings, Deadline, Result
from .planner import plan_query
from .network import Fetcher
from .parser import parse_response
from .resolvers import resolve
from .search import search
from .knowledge import lookup
from .candidates import extract, rank, verify, conflicts, passage_score, overlap
from .selector import select, verify_selection, verify_proof
from .proofs import propose as propose_proof, validate as validate_proof
from .urls import canonical_url, same_site,discovery_url,unique_links,relevance_url,answer_lookup_url
from .normalize import clean,iso_date
from .evidence import eligible
from .oyez import adapt_case, case_key, rendered_case_supported, unrendered_passages
from .familysearch import adapt_profile
from .github_history import request as github_history_request, pair as github_history_pair


def link_score(plan, source, url, anchor, hints=()):
    if answer_lookup_url(url) and not re.search(r'\b(?:crosswords?|clues?|puzzles?)\b',plan.question,re.I):
        return -10
    ranking_url=relevance_url(url)
    score = overlap(plan.terms, anchor) * 3 + overlap(plan.terms, ranking_url) * 1.3
    score += overlap(plan.attributes, anchor + " " + ranking_url) * 0.8
    from .planner import tokens
    score += overlap([word for hint in hints for word in tokens(hint)],anchor+' '+ranking_url)*2.5
    if same_site(source, url):
        score += 1
    if re.search(r"login|sign.in|privacy|terms|cart|facebook|twitter|linkedin", ranking_url, re.I):
        score -= 8
    if plan.versions and not any(v in ranking_url + " " + anchor for v in plan.versions):
        score -= 1
    if re.search(r"contact|support|spec|pricing|release|download|about|reference|license", ranking_url + " " + anchor, re.I):
        score += 1
    return score


def dump_pages(question, pages):
    """Diagnostics only: APERTURE_DUMP_PAGES=<dir> saves the parsed pages a query read."""
    folder = os.environ.get('APERTURE_DUMP_PAGES')
    if not folder:
        return
    try:
        import hashlib, json
        os.makedirs(folder, exist_ok=True)
        name = hashlib.sha256(question.encode('utf-8')).hexdigest()[:16] + '.json'
        with open(os.path.join(folder, name), 'w', encoding='utf-8') as handle:
            json.dump({'question': question, 'pages': [asdict(p) for p in pages]}, handle, ensure_ascii=False)
    except Exception:
        pass


def rank_pages(plan, pages, extracted):
    """Extract once per page, then rank. rank() mutates scores, so cached candidates are copied.
    Runs in a worker thread: large pages made this block the event loop past the deadline."""
    candidates = []
    for page in pages:
        if page.url not in extracted:
            extracted[page.url] = list(extract(plan, page))
        candidates.extend(replace(c, signals=dict(c.signals)) for c in extracted[page.url])
    candidates = rank(candidates, plan)
    return candidates, rank_passages(plan, pages, candidates)


def rank_passages(plan,pages,candidates=()):
    # Table cells share row evidence; duplicates crowd useful passages out of the context.
    unique={}
    typed_evidence={(c.source,clean(c.evidence),clean(c.section)) for c in candidates
        if plan.kind in {'number','measurement','percentage','phone','email','date','year','price','duration','version'} and verify(c,plan,pages)}
    for page in pages:
        for passage in page.passages:
            if not eligible(plan,page,passage):continue
            key=(page.url,clean(passage.text),clean(passage.section))
            score=passage_score(plan,page,passage)
            if key in typed_evidence:score+=4
            if key not in unique or score>unique[key][2]:unique[key]=(page,passage,score)
    items=list(unique.values())
    weight=bm25_weight()
    if weight and len(items)>1:
        scores=bm25([(p,passage) for p,passage,s in items],plan)
        top=max(scores) or 1.0
        items=[(p,passage,s+weight*b/top) for (p,passage,s),b in zip(items,scores)]
    ranked=sorted(items,key=lambda x:x[2],reverse=True)
    if plan.kind=='text' and plan.operation=='single':ranked=diversify(ranked)
    return ranked


def diversify(ranked):
    """Open questions only read the first few passages. Identical text from mirror or revision URLs
    must not take two slots, and one page's infobox rows must not fill the window before prose does."""
    seen=set();counts={};out=[]
    for page,passage,score in ranked:
        text=clean(passage.text)
        if text in seen:continue
        seen.add(text)
        group=(page.url,passage.kind)
        counts[group]=counts.get(group,0)+1
        out.append((page,passage,score-3.0*max(0,counts[group]-2)))
    return sorted(out,key=lambda x:x[2],reverse=True)


def bm25_weight():
    try:return float(os.environ.get('APERTURE_BM25_WEIGHT','8'))
    except ValueError:return 8.0


def bm25(items,plan,k1=1.2,b=0.75):
    """IDF-weighted lexical relevance across every retrieved passage.

    Rare entity words outweigh topic words that occur in most passages of a page,
    and the page title is deliberately not part of the passage text."""
    from collections import Counter
    from .planner import tokens as tokenize, STOP as stop
    query=list(dict.fromkeys(t for t in plan.terms if t not in stop and len(t)>1))
    docs=[Counter(tokenize(f'{passage.label} {passage.section} {passage.text}')) for page,passage in items]
    lengths=[sum(doc.values()) or 1 for doc in docs]
    average=sum(lengths)/len(lengths)
    count=len(docs)
    idf={}
    for term in query:
        df=sum(1 for doc in docs if term in doc)
        idf[term]=math.log(1+(count-df+.5)/(df+.5))
    return [sum(idf[t]*doc[t]*(k1+1)/(doc[t]+k1*(1-b+b*length/average)) for t in query if t in doc)
            for doc,length in zip(docs,lengths)]


def bounded_links(links,pages,target=''):
    selected=unique_links((u,a) for score,u,a in links if score>1 or u==target)[:4]
    if selected:return selected,''
    origins={(urlsplit(page.url).scheme,urlsplit(page.url).netloc) for page in pages}
    weak=[(u,a) for score,u,a in links if score>=0 and (urlsplit(u).scheme,urlsplit(u).netloc) in origins]
    # A landing page often says only 'More'/'Details'. Follow at most two
    # same-origin pages, retaining the existing page/depth/deadline bounds.
    return unique_links(weak)[:2],'bounded_same_origin' if weak else ''


def recover_origins(frontier,pending,events,providers=(),target=''):
    """Revisit a search queue after content responses reveal a denied origin.

    This is a soft ordering preference, not a blacklist. Keep every pending
    source and the same batch size, including explicit navigation targets.
    """
    refusals={};readable=set()
    def origin(url):
        try:
            parsed=urlsplit(canonical_url(url))
            return (parsed.scheme,parsed.netloc) if parsed.scheme in {'http','https'} and parsed.netloc else None
        except ValueError:return None
    for event in events:
        requested=event.get('url','');final=event.get('final') or requested
        if discovery_url(requested) or discovery_url(final) or any(requested.startswith(prefix) for prefix,name in providers):continue
        key=origin(final)
        if not key:continue
        if event.get('status')==403 and event.get('error'):
            refusals.setdefault(key,set()).add(canonical_url(final))
        elif event.get('status')==200 and not event.get('error'):readable.add(key)
    # A single protected URL does not characterize its whole origin. A
    # successful content read also keeps that origin in its original order.
    denied={key for key,urls in refusals.items() if len(urls)>=2 and key not in readable}
    if not denied or not frontier:return frontier,pending,None
    ordered=unique_links([*frontier,*pending])
    chosen=[item for item in ordered if item[0]==target]
    remaining=[item for item in ordered if item[0]!=target]
    reordered=chosen+[item for item in remaining if origin(item[0]) not in denied]+[
        item for item in remaining if origin(item[0]) in denied]
    active,waiting=reordered[:len(frontier)],reordered[len(frontier):]
    if active==frontier and waiting==pending:return frontier,pending,None
    return active,waiting,{'denied_origins':[scheme+'://'+netloc for scheme,netloc in sorted(denied)],
        'previous_batch':[u for u,a in frontier],'next_batch':[u for u,a in active],
        'pending_count':len(waiting),'navigation_target':target}


class Engine:
    def __init__(self, settings=None):
        self.settings = settings or Settings.from_env()

    async def run(self, question, url=""):
        deadline = Deadline(self.settings.budget)
        plan = plan_query(question, url)
        trace = {"plan": asdict(plan), "errors": [], "selector": [], "timings": {}, "search_requests": 0, "llm_calls": 0}
        pages, attempted = [], set()
        if os.environ.get('APERTURE_DUMP_PAGES'):
            trace['_dump'] = (question, pages)
        extracted = {}
        navigation_hints=None
        search_recovered=False
        result = Result(diagnostics=trace)
        if not question or not str(question).strip():
            result.reason = "empty_question"
            return result
        if plan.temporal_issue:
            result.reason=plan.temporal_issue
            trace['reader_state']='not_run'
            return result
        async with Fetcher(self.settings, deadline) as fetcher:
            try:
                async with asyncio.timeout(deadline.timeout(self.settings.budget)):
                    t = time.monotonic()
                    direct, definitive = await resolve(plan, fetcher)
                    pages.extend(p for p in direct if not p.error)
                    trace['content_pages']=len({p.url for p in pages if not discovery_url(p.url)})
                    trace["timings"]["resolver"] = time.monotonic()-t
                    github_history=github_history_request(plan)[0]
                    crate_history=any(p.identity.get('registry')=='crates' and p.identity.get('historical_release') for p in pages)
                    if github_history and not github_history_pair(plan,pages):
                        result.reason='github_history_unavailable'
                        return self._trace(result,fetcher,deadline)
                    if definitive and not pages:
                        result.reason = 'authoritative_not_found_or_identity_mismatch'
                        return self._trace(result, fetcher, deadline)
                    candidates = rank([c for p in pages for c in extract(plan, p)], plan)
                    # A resolver is definitive only for the matching attribute with real candidates.
                    if plan.operation=='single' and definitive and candidates and candidates[0].score >= 6.5 and plan.kind != "text":
                        registry_pages = [p for p in pages if p.identity.get('registry') in {'pypi', 'npm'}]
                        if registry_pages:
                            candidates = self._registry_candidates(candidates, plan, registry_pages)
                        result = self._finish(candidates, plan, pages, result)
                        if result.answer:
                            result.reason = "direct_source"
                            return self._trace(result, fetcher, deadline)
                    seeds = []
                    if plan.url and not github_history and not crate_history:
                        u = canonical_url(plan.url)
                        if u:
                            seeds.append((u, "start URL"))
                    if not seeds and not candidates and self.settings.search and not github_history and not crate_history:
                        navigation_hints=await self._query_hints(plan,deadline,trace)
                        request=search(plan,fetcher,self.settings.search_providers,hints=navigation_hints) if navigation_hints else search(plan,fetcher,self.settings.search_providers)
                        discovered, searched = await asyncio.gather(lookup(plan, fetcher),request)
                        seeds = unique_links(discovered + searched)
                        search_recovered=True
                    frontier = seeds[:4]
                    discovery_pending=seeds[4:]
                    model_abstained = False
                    reader_state = 'not_run'
                    proof_required=plan.operation!='single'
                    for depth in range(self.settings.max_depth+1):
                        if deadline.remaining < 0.7:
                            break
                        urls = []
                        for u, anchor in frontier:
                            if u not in attempted and len(attempted) < self.settings.max_pages:
                                attempted.add(u)
                                urls.append(u)
                        if not urls and depth>0:
                            break
                        initial_timeout=min(8,max(.5,deadline.remaining-6)) if depth==0 else self.settings.request_timeout
                        responses = await asyncio.gather(*(fetcher.fetch(u,timeout=initial_timeout) for u in urls))
                        for requested_url, resp in zip(urls, responses):
                            page = await adapt_case(requested_url, resp, fetcher)
                            if page is None:
                                page = await adapt_profile(requested_url,resp,fetcher,attempted)
                            if page is None:
                                # Large articles parse for ~0.5 s each; keep the event loop free so the deadline can fire.
                                page = await asyncio.to_thread(parse_response, resp)
                            if page.error:
                                trace["errors"].append({"url": page.url, "error": page.error})
                                continue
                            # The API is already in the guarded fetch cache. If
                            # time permits, cite the frontend only after Chromium
                            # actually renders matching case content at that URL.
                            if (page.identity.get('registry') == 'oyez' and self.settings.browser
                                    and case_key(requested_url) and urlsplit(requested_url).hostname != 'api.oyez.org'
                                    and deadline.remaining > 8.5):
                                from .browser import render
                                rendered, browser_state = await render(requested_url, self.settings, deadline, fetcher)
                                matched = rendered_case_supported(page, rendered)
                                trace.setdefault('browser', []).append({**browser_state,
                                    'purpose':'oyez_case_citation', 'content_matched':matched})
                                if matched:
                                    extra = unrendered_passages(page, rendered)
                                    if extra and not any(p.url == page.url for p in pages):
                                        pages.append(replace(page, passages=extra))
                                    page = rendered
                            # Raw HTML may expose embedded state even when the display is JS-only.
                            is_html='html' in resp.content_type.casefold() or page.dynamic
                            if is_html and (not page.passages or page.dynamic) and self.settings.browser:
                                from .browser import render
                                rendered, browser_state = await render(page.url, self.settings, deadline, fetcher)
                                trace.setdefault('browser',[]).append(browser_state)
                                if rendered:
                                    page = rendered
                            if not any(p.url == page.url for p in pages):
                                pages.append(page)
                        trace['content_pages']=len({p.url for p in pages if not discovery_url(p.url)})
                        rank_started = time.monotonic()
                        candidates, ranked_passages = await asyncio.to_thread(
                            rank_pages, plan, list(pages), extracted)
                        trace.setdefault('timings', {}).setdefault('rank_seconds', []).append(
                            round(time.monotonic() - rank_started, 3))
                        proof,proof_required=propose_proof(plan,pages)
                        if (github_history and not proof and self.settings.model_url and deadline.remaining>2.4):
                            chosen,state=await select(plan,[],ranked_passages,self.settings,deadline)
                            trace['llm_calls']+=1
                            trace['selector'].append(state)
                            if chosen:
                                trace.setdefault('model_selections',[]).append(asdict(chosen))
                                proof,proof_required=propose_proof(plan,pages,chosen)
                        if proof_required:
                            trace['proof_state']='incomplete'
                            model_abstained=True
                        if proof and validate_proof(proof,plan,pages):
                            trace['proposed_proof']=asdict(proof)
                            trace['proof_state']='awaiting_semantics'
                            if self.settings.model_url and deadline.remaining>1.2:
                                supported,check=await verify_proof(plan,proof,pages,self.settings,deadline,ranked_passages)
                                trace['llm_calls']+=1
                                trace.setdefault('proof_verification',[]).append(check)
                                reader_state='selected' if supported else 'no_evidence' if check=='unsupported' else self._reader_state(check)
                                if supported:
                                    trace['proof_state']='verified'
                                    trace['reader_state']='answered'
                                    result.answer,result.sources=proof.answer,proof.sources
                                    result.evidence='\n'.join(dict.fromkeys(atom.span for atom in proof.atoms))
                                    result.reason='proof_verified'
                                    return self._trace(result,fetcher,deadline)
                                trace['proof_state']='semantic_rejection' if check=='unsupported' else reader_state
                            else:
                                reader_state='budget_exhausted' if self.settings.model_url else 'not_run'
                                trace['proof_state']=reader_state if self.settings.model_url else 'model_disabled'
                        bound=[c for c in candidates if c.signals.get('structure')=='signature' and verify(c,plan,pages)]
                        if bound and not proof_required and re.search(r'\bdefault\b',plan.question,re.I):
                            result=self._finish(bound,plan,pages,result)
                            if result.answer:
                                result.reason='literal_parameter_binding'
                                return self._trace(result,fetcher,deadline)
                        chronology=[c for c in candidates if verify(c,plan,pages)]
                        if not proof_required and plan.kind=='version' and plan.as_of and chronology and not any(p.truncated for p in pages):
                            def dated_field(c):
                                dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',c.evidence+' '+c.section)
                                return (c.signals.get('structure') in {'cell','field','json'}
                                    and re.fullmatch(r'(?:stable )?(?:version|release)',c.label,re.I)
                                    and dates and all(iso_date(d) and d<=plan.as_of for d in dates))
                            if all(dated_field(c) for c in chronology):
                                result=self._finish(chronology,plan,pages,result)
                                if result.answer:
                                    result.reason='dated_release_table'
                                    return self._trace(result,fetcher,deadline)
                        # Reserve a single semantic read after initial retrieval when evidence is rich.
                        # The selector sees one window of passages. When it abstains and time remains,
                        # page through the next window with the same literal-span and verification gates.
                        for window in range(2):
                            if proof_required or not self.settings.model_url or not ranked_passages or deadline.remaining <= 1.2:
                                break
                            if window:
                                if (reader_state not in {'no_evidence', 'evidence_rejected'} or len(ranked_passages) <= 8
                                        or deadline.remaining < 7):
                                    break
                                window_passages, window_candidates = ranked_passages[8:16], []
                            else:
                                window_passages, window_candidates = ranked_passages, candidates
                            chosen, state = await select(plan, window_candidates, window_passages, self.settings, deadline)
                            trace["llm_calls"] += 1
                            trace["selector"].append(state)
                            reader_state = self._reader_state(state)
                            model_abstained = chosen is None
                            if chosen:
                                trace.setdefault('model_selections',[]).append(asdict(chosen))
                                # A semantic selection failing evidence/type constraints must not
                                # silently turn into a different deterministic answer.
                                if not verify(chosen,plan,pages):
                                    model_abstained=True
                                    reader_state='evidence_rejected'
                            if chosen and verify(chosen, plan, pages):
                                if self._ambiguous(candidates,plan,pages,chosen):
                                    result.reason='unresolved_conflict'
                                    return self._trace(result, fetcher, deadline)
                                if deadline.remaining > 1.2:
                                    supported,check=await verify_selection(plan,chosen,window_passages,self.settings,deadline)
                                    trace['llm_calls']+=1
                                    trace.setdefault('verification',[]).append(check)
                                    if supported:
                                        trace['reader_state']='answered'
                                        result = self._chosen(chosen, result, "model_verified")
                                        return self._trace(result, fetcher, deadline)
                                    model_abstained=True
                                    reader_state='no_evidence' if check=='unsupported' else self._reader_state(check)
                                else:
                                    trace.setdefault('verification',[]).append('budget_unavailable')
                                    model_abstained=True
                                    reader_state='budget_exhausted'
                        # General lexical candidates need a successful semantic read.
                        # Independent API/signature/date proofs are handled before this gate.
                        if candidates and not proof_required and not self.settings.model_url:
                            result = self._finish(candidates, plan, pages, result)
                            if result.answer and candidates[0].score >= 8 and not conflicts(candidates):
                                return self._trace(result, fetcher, deadline)
                        if depth == self.settings.max_depth or github_history or len(attempted) >= self.settings.max_pages:
                            break
                        links = []
                        service_failed = reader_state in {'service_unavailable', 'invalid_reply', 'budget_exhausted'}
                        if navigation_hints is None and self.settings.model_url and not service_failed and sum(len(p.links) for p in pages)>40 and deadline.remaining>4:
                            from .navigation import expand_navigation
                            navigation_hints,hints_state=await expand_navigation(plan,self.settings,deadline)
                            trace['llm_calls']+=1
                            trace['navigation_hints']=navigation_hints
                            trace['navigation_hint_state']=hints_state
                        for page in pages:
                            for target, anchor in page.links:
                                if target not in attempted:
                                    links.append((link_score(plan, page.url, target, anchor,navigation_hints or ()), target, anchor))
                        links.sort(reverse=True)
                        unique_ranked={}
                        for item in links:unique_ranked.setdefault(item[1],item)
                        links=list(unique_ranked.values())
                        target=''
                        possible,fallback=bounded_links(links,pages)
                        only_choice=len(links)==1 and bool(possible)
                        if links and not only_choice and self.settings.model_url and not service_failed and deadline.remaining>2:
                            from .navigation import suggest_link
                            target,state=await suggest_link(plan,links,self.settings,deadline)
                            trace['llm_calls']+=1
                            trace.setdefault('navigation',[]).append({'state':state,'chosen':target})
                            if target:
                                links.sort(key=lambda item:item[1]==target,reverse=True)
                        frontier,fallback=bounded_links(links,pages,target)
                        if fallback:trace.setdefault('navigation_fallback',[]).append({'depth':depth,'reason':fallback,'urls':[u for u,a in frontier]})
                        if search_recovered and frontier:
                            pending=unique_links(item for item in discovery_pending if item[0] not in attempted
                                and item[0] not in {u for u,a in frontier})
                            if pending:
                                # Four links on one answerless landing page must
                                # not starve the remaining independent results.
                                # Keep navigation (including its chosen target)
                                # while reserving two slots in the same batch.
                                frontier=unique_links(pending[:2]+frontier)[:4]
                                trace.setdefault('discovery_reserve',[]).append({'depth':depth,
                                    'urls':[u for u,a in pending[:2]]})
                        if self.settings.search and not search_recovered and deadline.remaining>5 and (not frontier or model_abstained or not candidates):
                            trace['search_recovery']='starting_url_unavailable_or_exhausted' if plan.url else 'initial_discovery_exhausted'
                            trace['search_recovery_depth']=depth
                            if navigation_hints is None and not service_failed:navigation_hints=await self._query_hints(plan,deadline,trace)
                            discovered=await search(plan,fetcher,self.settings.search_providers,hints=navigation_hints) if navigation_hints else await search(plan,fetcher,self.settings.search_providers)
                            discovered=unique_links(item for item in discovered if item[0] not in attempted)
                            if discovered:
                                frontier=unique_links(discovered[:2]+frontier[:2]) if frontier else discovered[:4]
                                discovery_pending=unique_links(discovery_pending+discovered)
                            search_recovered=True
                        # A search returns more than one four-page fetch batch.
                        # Retain unvisited results when earlier pages fail or have
                        # no answer, within the original page/depth/deadline caps.
                        frontier=unique_links(item for item in frontier if item[0] not in attempted)
                        queued=[item for item in discovery_pending if item[0] not in attempted and item[0] not in {u for u,a in frontier}]
                        refill=queued[:max(0,4-len(frontier))]
                        frontier+=refill
                        scheduled={u for u,a in frontier}
                        discovery_pending=[item for item in queued if item[0] not in scheduled]
                        if refill:trace.setdefault('discovery_refill',[]).append({'depth':depth,'urls':[u for u,a in refill]})
                        frontier,discovery_pending,recovery=recover_origins(frontier,discovery_pending,
                            fetcher.events,self.settings.search_providers or (),target)
                        if recovery:trace.setdefault('origin_recovery',[]).append({'depth':depth,**recovery})
                        if not frontier:
                            break
                    trace['reader_state'] = reader_state
                    if proof_required:
                        result=Result(reason='proof_'+trace.get('proof_state','incomplete'),diagnostics=trace)
                    elif self.settings.model_url:
                        result = Result(reason='model_' + reader_state, diagnostics=trace)
                    elif candidates:
                        result = self._finish(candidates, plan, pages, result)
                    else:
                        result.reason = "no_supported_candidate"
                    trace["top_candidates"] = [asdict(c) for c in candidates[:8]]
                    trace["conflicts"] = conflicts(candidates)
            except TimeoutError:
                trace["errors"].append({"error": "internal_deadline"})
                result.reason = "deadline_best_evidence" if result.answer else "deadline_no_evidence"
            except Exception as exc:
                # The process adapter additionally survives parser/library errors. Record rather than hide.
                trace["errors"].append({"error": type(exc).__name__, "message": str(exc)[:300],
                    'traceback':traceback.format_exc(limit=6)})
                result.reason = "engine_error"
            return self._trace(result, fetcher, deadline)

    async def _query_hints(self,plan,deadline,trace):
        if not self.settings.model_url or deadline.remaining<7:return []
        from .navigation import expand_navigation
        hints,state=await expand_navigation(plan,self.settings,deadline)
        trace['llm_calls']+=1
        trace['search_hints']=hints
        trace['search_hint_state']=state
        return hints

    @staticmethod
    def _reader_state(state):
        if state in {'candidate', 'span'}:return 'selected'
        # Capacity is specific to this evidence request. The endpoint can still
        # serve smaller navigation requests within the existing retrieval caps.
        if state == 'model_context_limit':return 'context_limit'
        if state=='incomplete_proof_context':return 'no_evidence'
        if state == 'abstain':return 'no_evidence'
        if state in {'budget_exhausted', 'model_deadline', 'model_cancelled', 'TimeoutError'}:return 'budget_exhausted'
        if state.startswith(('invalid_', 'model_invalid_')) or state in {'invalid_json', 'oversized_reply'}:return 'invalid_reply'
        return 'service_unavailable'

    @staticmethod
    def _registry_candidates(candidates, plan, pages):
        # These adapters have checked the response identity. Only an exact
        # scalar registry field can answer without a semantic model decision.
        labels = {'version': {'current stable version', 'version', 'stable version'},
                  'license': {'license', 'license expression'}, 'email': {'author email'},
                  'url': {'homepage URL', 'homepage'}}.get(plan.kind, set())
        if plan.as_of or plan.year or re.search(r'\b(?:and|versus|compare|difference|between)\b', plan.question, re.I):
            return []
        return [c for c in candidates if any(p.url == c.source and any(
            f.locator.startswith('adapter/') and f.label in labels and f.label == c.label
            and clean(f.value) == clean(c.raw) and f.text == c.evidence for f in p.passages) for p in pages)]

    @staticmethod
    def _chosen(c, result, reason):
        result.diagnostics["selection"] = asdict(c)
        result.answer, result.sources, result.evidence, result.reason = c.answer, [c.source], c.evidence, reason
        result.confidence = round(min(0.97, 0.55 + max(0, c.score) * 0.025), 3)
        return result
    def _finish(self, candidates, plan, pages, result):
        strong = [c for c in candidates if c.score >= 5.5 and verify(c, plan, pages)]
        if not strong:
            result.answer, result.sources, result.confidence, result.evidence = "", [], 0, ""
            result.reason = "insufficient_alignment"
            return result
        # Exact ties on a single requested field require disambiguation, not random DOM order.
        if self._ambiguous(strong,plan,pages):
            result.answer, result.sources, result.confidence, result.evidence = "", [], 0, ""
            result.reason = "unresolved_conflict"
            return result
        return self._chosen(strong[0], result, "deterministic_verified")

    @staticmethod
    def _ambiguous(candidates,plan,pages,chosen=None):
        if plan.kind=='version' and plan.latest:return False
        valid=[c for c in candidates if verify(c,plan,pages)]
        strong=[c for c in valid if c.score>=5.5]
        def context(c):return clean(c.evidence.replace(c.raw,'<VALUE>')).casefold()
        anchor=chosen or (strong[0] if strong else None)
        if anchor and anchor.signals.get('structure')=='record':
            # Compare the selected record's actual slot, even when an unrelated
            # metadata candidate ranked above it. DOM order cannot settle two
            # different values in otherwise identical subject/scope records.
            values={c.answer for c in valid if c.signals.get('structure')=='record'
                and clean(c.section).casefold()==clean(anchor.section).casefold() and context(c)==context(anchor)}
            if len(values|{anchor.answer})>1:return True
        if not strong:return False
        # A model-selected answer must not be vetoed by ties in some other
        # field (for example infobox title/media labels above a composer span).
        if chosen:
            if not chosen.label:return False
            top=next((c for c in strong if c.source==chosen.source and c.raw==chosen.raw
                and clean(c.evidence)==clean(chosen.evidence)),chosen)
        else:top=strong[0]
        return bool(top.label and any(c.label==top.label and c.answer!=top.answer
            and context(c)==context(top) and abs(c.score-top.score)<0.15 for c in strong))

    @staticmethod
    def _trace(result, fetcher, deadline):
        dump = result.diagnostics.pop('_dump', None)
        if dump:
            dump_pages(*dump)
        result.diagnostics["fetches"] = fetcher.events
        result.diagnostics['http_responses_success']=sum(1 for e in fetcher.events if not e['error'])
        result.diagnostics["pages_fetched"] = result.diagnostics.get('content_pages',0)
        custom=fetcher.settings.search_providers or []
        result.diagnostics["search_requests"] = sum(discovery_url(e['url']) or any(e['url'].startswith(prefix) for prefix,name in custom) for e in fetcher.events)
        result.diagnostics["seconds"] = round(time.monotonic()-deadline.start, 4)
        if deadline.model_capacity_skips:
            result.diagnostics['model_capacity_skips'] = deadline.model_capacity_skips
        return result
