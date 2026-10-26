# Name-boundary proposal: not promoted

This investigation started from the actual exposed `simpleqa-911` trace. The
model selected `former Ryuhoku Elementary School` from a paragraph that twice
describes the first planting site. The school entity and source already match
the question. The proposed change shortened lowercase status descriptors for
explicit facility-name requests, preserving quoted/formally declared names,
capitalized titles, status-sensitive questions and non-name requests.

The authored CPU HTTP controls passed **17/21 before, 21/21 with the proposal**.
Those are controls of the proposed formatting policy, not independent questions.
Source/semantic verification remained mandatory. The exact proposed helper is
saved at `eval/proposals/name-boundaries-20261023.py.txt`; its selector change
is saved as `eval/proposals/name-boundaries-20261023.patch`. Both production
changes were removed after inspecting the real replay.

`eval/diagnose_name_capture.py` verifies the original source capture SHA,
reuses the original question and source-assisted starting URL, and feeds the
original selected span through an explicit CPU semantic stub. The replay's
`capture-replay-v1.json` passes 7/8 behavior assertions: the proposed output
still fails the unchanged strict scorer. The original gold is
`Ryuhoku Elementary School.` with a trailing period; the proposed output is
`Ryuhoku Elementary School`. Both before and proposed after fail exact answer
comparison while retaining an accepted source. This is not a recovered point.

Adding a period to match this specific gold would not establish a general
name rule. The old answer is already a supported reference to the correct
school, so removing its descriptive adjective does not prove an improvement
in factual retrieval either. The proposal adds a heuristic with possible
proper-name errors. It is therefore **not promoted**, despite green authored
controls. The frozen gold, aliases, first assessment, strict scorer and
production name handling remain unchanged.

The diagnostics and failed replay are retained as proposal artifacts, not
required production regression gates. To reproduce the proposed behavior,
use the saved helper/patch in an isolated development checkout; their runtime
source hashes are recorded in the original after artifacts. Do not reapply
automatically or claim it raises the latest external score above 0/12.

No GPU, resident model, browser, public request, paid API, build or submission
was used in this proposal investigation. The next work should target missing
answer evidence or demonstrated service/retrieval defects rather than tuning
punctuation for one exposed reference string.
