"""Audit heuristic confidence and selective risk; does not tune production thresholds."""
import argparse
import json
from pathlib import Path


def confidence(row):
    if not row.get('answer'):return None
    if isinstance(row.get('confidence'),(float,int)):
        return max(0.,min(1.,float(row['confidence'])))
    score=row.get('diagnostics',{}).get('selection',{}).get('score')
    if isinstance(score,(float,int)):
        # The shipping _chosen mapping is retained unchanged in the source.
        # Older harnesses did not store Result.confidence itself.
        return round(min(.97,.55+max(0,score)*.025),3)
    return None


def analyze(rows):
    pairs=[(value,bool(row['joint_ok'])) for row in rows if (value:=confidence(row)) is not None]
    bins=[];ece=0.
    for index in range(10):
        group=[(p,y) for p,y in pairs if index/10<=p<(index+1)/10 or index==9 and p==1]
        if not group:continue
        mean=sum(p for p,y in group)/len(group);accuracy=sum(y for p,y in group)/len(group)
        ece+=len(group)*abs(mean-accuracy)/max(1,len(pairs))
        bins.append({'lower':index/10,'upper':(index+1)/10,'n':len(group),'mean_confidence':mean,'joint_accuracy':accuracy})
    thresholds=[]
    for threshold in (0,.55,.7,.8,.85,.9,.95,.97):
        kept=[(p,y) for p,y in pairs if p>=threshold]
        correct=sum(y for p,y in kept)
        thresholds.append({'threshold':threshold,'retained':len(kept),'coverage_all_cases':len(kept)/max(1,len(rows)),
            'joint_precision_when_retained':correct/len(kept) if kept else None,'retained_errors':len(kept)-correct,
            'correct_all_cases':correct/max(1,len(rows))})
    return {'n':len(rows),'answered':sum(bool(row.get('answer')) for row in rows),'confidence_available':len(pairs),
        'brier_answered_joint':sum((p-int(y))**2 for p,y in pairs)/len(pairs) if pairs else None,
        'ece_answered_joint':ece if pairs else None,'bins':bins,'selective_risk':thresholds}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('results',nargs='+');parser.add_argument('--out',required=True);args=parser.parse_args()
    reports=[]
    for name in args.results:
        data=json.loads(Path(name).read_text(encoding='utf-8'))
        reports.append({'result':name,**analyze(data['rows'])})
    output={'interpretation':'Diagnostic only. Confidence is a heuristic, not a calibrated probability. Older rows reconstruct the unchanged shipping score mapping from recorded selection scores. Answered-only calibration targets exact answer AND source correctness; it does not assign a probability to an abstention. Fixed threshold curves do not change production decisions or gold.',
        'reports':reports}
    Path(args.out).write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps([{'result':r['result'],'n':r['n'],'answered':r['answered'],'ece':r['ece_answered_joint']} for r in reports]))


if __name__=='__main__':main()
