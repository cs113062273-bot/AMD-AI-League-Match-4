"""Validate the resident selector boundary without importing any ML dependency."""
from .normalize import clean
from .members import member_count, literal_members, join_members
from .cardinals import source_span as count_span
from .phones import complete as complete_phone


def valid_request(data):
    if not isinstance(data, dict) or not isinstance(data.get('question'), str):
        return False
    if len(data['question']) > 20_000 or not isinstance(data.get('constraints', {}), dict):
        return False
    for name, fields, limit in [('candidates', ('value','evidence'), 14), ('passages', ('text',), 8)]:
        entries = data.get(name, [])
        if not isinstance(entries, list) or len(entries) > limit:
            return False
        seen = set()
        for entry in entries:
            if not isinstance(entry, dict) or type(entry.get('id')) is not int or entry['id'] < 0 or entry['id'] in seen:
                return False
            seen.add(entry['id'])
            if any(field not in entry or not isinstance(entry[field],str) or len(entry[field])>5000 for field in fields):
                return False
    return True


def validate_reply(reply, request):
    invalid = {'candidate': -1, 'passage': -1, 'answer': '', 'error': 'invalid_selection'}
    if isinstance(reply, dict) and 'answers' in reply:
        constraints = request.get('constraints', {})
        kind, operation = constraints.get('kind', 'text'), constraints.get('operation', 'single')
        expected = member_count(request.get('question', ''), kind, operation)
        p = reply.get('passage')
        c = reply.get('candidate', -1)
        if (not expected or type(constraints.get('member_count')) is not int
                or constraints['member_count'] != expected or type(p) is not int or type(c) is not int or c != -1):
            return invalid
        if p == -1 and reply['answers'] == [] and reply.get('answer', '') == '':
            return {'candidate': -1, 'passage': -1, 'answer': ''}
        evidence = next((item for item in request.get('passages', []) if item['id'] == p), None)
        values = literal_members(request['question'], reply['answers'], evidence['text'], kind, operation) if evidence else None
        if values and isinstance(reply.get('answer', ''), str) and reply.get('answer', '') in {'', join_members(values)}:
            return {'candidate': -1, 'passage': p, 'answer': join_members(values), 'answers': values}
        return invalid
    if isinstance(reply,dict) and 'candidate' not in reply and not request.get('candidates'):
        reply={**reply,'candidate':-1}
    if isinstance(reply,dict) and not request.get('candidates') and reply.get('answer')=='':
        # A blank extractive answer is safe abstention even if the model leaves a
        # passage id populated. Treating it as a transport error would enable fallback.
        return {'candidate':-1,'passage':-1,'answer':''}
    if not isinstance(reply, dict) or type(reply.get('candidate')) is not int or type(reply.get('passage')) is not int or not isinstance(reply.get('answer'), str):
        return {**invalid, 'error':'invalid_schema'}
    c, p, answer = reply['candidate'], reply['passage'], reply['answer']
    if c == -1 and p == -1 and answer == '':
        return {'candidate':c, 'passage':p, 'answer':answer}
    if request.get('constraints', {}).get('member_count'):
        return invalid
    candidate=next((item for item in request.get('candidates',[]) if item['id']==c),None)
    if p == -1 and candidate and (answer=='' or clean(answer)==clean(candidate['value'])):
        # Redundant value is safe only when it exactly agrees with the transmitted
        # candidate. Conflicting values and candidate+passage mixtures remain errors.
        if request.get('constraints',{}).get('kind') == 'phone' and not complete_phone(candidate['value'],candidate.get('evidence','')):return invalid
        return {'candidate':c, 'passage':p, 'answer':''}
    if c == -1 and 0 < len(answer) <= 350:
        evidence = next((item for item in request.get('passages', []) if item['id'] == p), None)
        kind = request.get('constraints', {}).get('kind', 'text')
        span=count_span(answer,evidence['text'],request.get('question',''),kind,
                        request.get('constraints',{}).get('operation','single')) if evidence else None
        if span is not None:
            if kind == 'phone' and not complete_phone(span,evidence['text']):return invalid
            return {'candidate':c, 'passage':p, 'answer':span}
    return invalid
