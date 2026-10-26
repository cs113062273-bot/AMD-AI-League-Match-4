"""Side-by-side scoring of an eval/run.py result. Never replaces the strict headline score.

Columns: strict (as eval/run.py), normalized (case, spacing, trailing punctuation),
range (numeric answer inside the gold row's own "acceptable range: anything between A and B").
Gold answers, aliases and the strict scorer are untouched."""
import json
import re
import sys

RANGE = re.compile(r'acceptable range:\s*anything between\s+([\d,\.]+)\w*\s+and\s+([\d,\.]+)', re.I)
NUMBER = re.compile(r'-?\d[\d,]*(?:\.\d+)?')


def norm(text):
    text = str(text or '').casefold().replace('’', "'").replace('‘', "'").replace('&', ' and ')
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'^(?:the|a|an)\s+', '', text)
    return text.strip(' .,;:!?"\'')


def to_number(text):
    try:
        return float(text.replace(',', ''))
    except ValueError:
        return None


def score_row(row):
    gold = row['expected_answer'][0] if row['expected_answer'] else ''
    base = re.sub(r'\s*\(acceptable range:.*\)\s*$', '', gold, flags=re.I)
    answer = row['answer']
    strict = bool(row['answer_ok'])
    normalized = strict or (bool(answer) and norm(answer) in {norm(g) for g in [*row['expected_answer'], base]})
    in_range = False
    match = RANGE.search(gold)
    if answer and match:
        low, high = to_number(match[1]), to_number(match[2])
        numbers = [to_number(n) for n in NUMBER.findall(answer)]
        # The first number is the claimed value; later numbers are usually units or dates.
        in_range = bool(numbers and numbers[0] is not None and low is not None and high is not None
                        and low <= numbers[0] <= high)
    return strict, normalized, normalized or in_range


def main(path):
    data = json.load(open(path, encoding='utf-8'))
    rows = data['rows']
    totals = [0, 0, 0]
    for row in rows:
        for i, ok in enumerate(score_row(row)):
            totals[i] += ok
    n = len(rows)
    answered = sum(bool(r['answer']) for r in rows)
    print(json.dumps({'n': n, 'strict': totals[0], 'normalized': totals[1], 'range_aware': totals[2],
                      'answered': answered,
                      'precision_when_answered_range_aware': round(totals[2] / answered, 3) if answered else None,
                      'source_in_gold': sum(bool(r['source_ok']) for r in rows)}, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
