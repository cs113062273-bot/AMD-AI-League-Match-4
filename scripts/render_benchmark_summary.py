"""Render a concise ledger directly from retained benchmark result files."""
import json
from pathlib import Path


def load(name):
    path=Path('benchmarks')/(name+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def main():
    lines=['# Measurements and provenance','',
        'These are local measurements, not official Match 4 scores. Exact joint success requires both an accepted answer and an exact predeclared source URL. Multiple predeclared URLs are alternatives; original reports under the earlier first-URL-only scorer remain unchanged. Empty answers require empty sources. No datasets are pooled into a headline accuracy.','',
        '## First frozen assessments','',
        '| Result | Cases | Answer | Source | Joint | p50 / p95 / max seconds | Exceptions / malformed / internal deadlines |',
        '|---|---:|---:|---:|---:|---|---|']
    def row(name,label):
        data=load(name)
        if not data:return False
        summary=data['summary'];latency=summary['latency']
        lines.append(f"| [{label}](benchmarks/{name}.json) | {summary['n']} | {summary['answer_accuracy']:.1%} | {summary['source_accuracy']:.1%} | {summary['joint_accuracy']:.1%} | {latency['p50']:.3f} / {latency['p95']:.3f} / {latency['max']:.3f} | {summary['crashes']} / {summary['malformed_outputs']} / {summary['internal_deadlines']} |")
        return True
    for name,label in [('holdout-rule','Original 20-family rules'),('holdout-model','Original 20-family hybrid'),
        ('final-holdout-model','Separate 30-page hybrid'),('transfer-frozen-first-model','Separate 20-page transfer hybrid'),
        ('external-simpleqa20-first','First external 20; now development'),('external-simpleqa100-first','First external 100; now development'),
        ('external-transfer100-first','New disjoint external 100; first run')]:row(name,label)
    lines+=['','The 100-case synthetic assessment has 20 families with five related variants, not 100 independent website designs. The 30-page and 20-page sets were independently written later by the same author, so author bias remains. The external 100 excludes every previously exposed external row and applies no host/topic/difficulty/availability filter. It is an adaptation of Google SimpleQA Verified, not its official autorater.','',
        '## Current regression and live measurements','',
        '| Result | Cases | Answer | Source | Joint | p50 / p95 / max seconds | Exceptions / malformed / internal deadlines |',
        '|---|---:|---:|---:|---:|---|---|']
    for stem,label in [('dev-model','Development families'),('holdout-model','Original holdout, now regression'),
        ('final-holdout-model','30-page set, now regression'),('transfer-frozen-model','20-page transfer, now regression'),
        ('live-model','Narrow primary-source live development'),('live-transfer-model','Broader live transfer, now development')]:
        names=[stem+'-'+tag for tag in ('finalonline','finaloffline','hardened','audited2','shipping')]
        name=next((name for name in names if load(name)),stem)
        row(name,label+' ('+name.rsplit('-',1)[-1]+')')
    lines+=['','Repeated or tuned sets are regression evidence. The hardened run competed with a large Docker base download: its fresh-CLI checks failed and its live scores deteriorated. That report remains failed. Offline fixture validation deliberately omits public-web claims; final online runs occur after large downloads. Fresh CLI checks and model lifecycle measurements are separate from in-process engine latency. The recovery attempt interrupted by a Unicode logging error has no completed aggregate score; see its retained log and failure analysis.','',
        '## Published competitor scoring','']
    name=next((name for tag in ('finalonline','hardened','audited2','shipping') if load(name:='public-pinpoint-comparison-'+tag)),'public-pinpoint-comparison')
    public=load(name)
    if public:lines.append(f"Aperture passes **{public['passed']}/{public['total']}** under the [published Pinpoint answer-only scorer](benchmarks/{name}.json). Its author reports 11/15 on an AMD W7900D, mean 7.9s and max 16.1s. Our hardware/network differ. The scorer uses loose substring matching and does not check source correctness, so this is neither a strict joint score nor a controlled superiority claim.")
    lines+=['','## Runtime and clean-room evidence','']
    name=next((name for tag in ('finalonline','finaloffline','hardened','audited2','shipping') if load(name:='local-gpu-validation-'+tag)),'local-gpu-validation')
    gpu=load(name)
    if gpu:
        health=gpu.get('health_after',gpu.get('health_before',{}))
        lines.append(f"[{name}](benchmarks/{name}.json): actual RTX 4070 SUPER execution, {health.get('parameters',0):,} parameters; cold start {gpu.get('cold_start_seconds',0):.3f}s; Torch peak {health.get('peak_vram_bytes',0):,} bytes; peak total device memory {gpu.get('peak_total_device_mib')} MiB; resident PID stable: {gpu.get('server_pid_stable')}. These are CUDA measurements, not AMD measurements.")
        lines.append('Report scope: '+gpu.get('scope','fixtures and public web')+'. Overall error: '+str(gpu.get('error','none'))+'.')
    lines+=['','The complete host test report, actual Linux Docker test/browser/CLI logs, production image size/lower-layer/inventory/archive receipts and actual AMD status are tracked in [AUDIT.md](AUDIT.md). `scripts/render_benchmark_summary.py` regenerates this ledger from the linked raw files.','',
        'See [methodology](docs/benchmark_methodology.md), [external provenance](docs/external_benchmark.md) and [failure analysis](docs/failure_analysis.md) for data freezes, scoring limits, ablations, first failures and remaining weaknesses.','']
    Path('BENCHMARKS.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Rendered BENCHMARKS.md from retained results')


if __name__=='__main__':main()
