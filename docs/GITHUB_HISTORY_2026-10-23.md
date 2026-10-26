# Bind historical GitHub license answers to a fetched commit and file

The previous resolver could answer a past-date license question with today's
repository metadata. Literal extraction and an always-positive semantic stub
did not catch that missing historical premise.

The new adapter uses the official [commit listing](https://docs.github.com/en/rest/commits/commits)
to select one commit before a cutoff, then reads the detected license file with
that exact SHA using the [license endpoint's ref parameter](https://docs.github.com/en/rest/licenses/licenses).
Owner/repository comparisons follow GitHub's documented case-insensitive names;
SHA, file paths, query references and source hosts remain exact.

- Validate the commit's repository URL, full SHA and complete UTC-normalizable
  committer timestamp. The date-only cutoff includes that whole UTC day, using
  the next midnight as the query bound and rejecting a commit at that boundary.
  A year-only question requires a commit in that year. Unsupported API date
  bounds, multiple results, missing times and future commits do not qualify.
- Read `/license?ref=<SHA>` only after a valid commit. Check the response status,
  requested URL, contents URL, blob URL, file type, base64 content, byte size and
  Git blob SHA-1. The hash checks internal file consistency; it is not an
  independent signature or historical-publication attestation.
- A classified SPDX identifier is a literal field premise. `NOASSERTION` and
  `NONE` do not become an answer such as `Other`. Instead, expose the decoded
  file paragraphs for literal semantic selection. No license-family answer
  mapping or benchmark alias table is used. Files exceeding the bounded reader
  size/paragraph count can be unavailable rather than partially trusted.
- A `github_license` proof binds a commit-date premise to a license premise
  through the same repository, SHA, blob and two fetched resource identities.
  Mechanical validation and independent semantic verification are mandatory.
  Unknown license text needs selection followed by proof verification. With
  the model disabled, the new proof abstains.
- Preserve both actual fetched API URLs as sources. Commit time stays in the
  commit response's passage; it is not appended as if present in the license
  response. Decoded paragraphs have `content/base64/paragraph/...` locators.
  A returned `download_url` is not represented as a fetched source.
- Missing/invalid history ends this adapter attempt before generic current
  metadata, frontend fetching or search can substitute for the missing proof.
  Ordinary current queries and separate dated external sources retain their
  existing paths. Explicit versions, tags, branches and deeper starting paths
  currently abstain rather than silently using default-branch history.

Public requests use no account, API key, credit card or paid wrapper. GitHub
documents [60 unauthenticated requests per hour](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
The adapter makes at most two API requests per attempt, skips the second if the
first reports zero remaining quota, and stops on 403/429. The shared fetcher
retains rate-limit headers and does not automatically retry GitHub API error
responses. Short budgets skip the historical attempt. Other hosts retain their
existing retry policy.

This is a bounded source policy, not a complete reconstruction of repository
history: listing commits uses history reachable from the current default
branch. Declared committer dates are not GitHub observation/publication times.
Deleted history, old branch heads, force pushes, tags and releases are not
reconstructed. The detected license file also does not resolve all licensing
statements elsewhere in a project.

## Evidence and limits

`eval/diagnose_github_history.py` uses actual loopback HTTP and explicitly
authored CPU semantic stubs; external hosts are blocked by its transport.
Final paired artifacts `github-history-20261023-before-v4.json` and
`github-history-20261023-after-v5.json` have the same diagnostic SHA:
**5/45 to 45/45**, 40 improved assertions and zero losses. These 45 related
controls are not independent questions or an unseen accuracy assessment.
They cover identified/decoded licenses, missing or mismatched history, Git
blob integrity, bad API shape, quota exhaustion, semantic rejection/service
failure, model-disabled abstention, conflicting subjects, unsupported refs,
question-only routing, year constraints, canonical repository casing, the
www frontend alias and the reader paragraph bound.
Earlier attempts remain recorded. The first 29-control implementation missed
the exhausted-quota case because the shared fetcher discarded that header;
retaining the header fixed the actual HTTP behavior.

`github-history-20261023-api-probe.json` records two actual, free, public API
requests for `psf/requests` at cutoff 2020-01-31. Their ignored research
captures retain complete response envelopes and hashes. The returned commit
was `d5c4cac0f4cc2f558099a55686ddb2e0bdc2dbd1`, dated
2020-01-25T23:19:22Z. The SHA-pinned file had classification `NOASSERTION`;
its decoded text contains `Apache License, Version 2.0`.

`eval/diagnose_github_capture.py` verifies those capture hashes, decodes the
saved HTTP envelopes, and replays their exact bodies without more API calls.
Final `github-history-20261023-capture-replay-v4.json` passes 3/3 compatibility
checks: CPU-stub-supported literal answer with both sources, semantic rejection,
and model-disabled abstention. The first replay artifact incorrectly passed
the saved envelope as the body (2/3); that harness mistake is preserved in v1,
corrected in v2, and the final production revision is recorded in v4.

Existing CPU regressions pass: proofs 27/27, registry history 43/43, cutoff
parsing 52/52, representative reader fixtures 15/15. No frozen question, gold
answer or alias changed; production imports no evaluation fixture or gold.
No GPU, resident model, browser, paid service, full benchmark sweep, build,
push or competition submission was used. No new held-out or model accuracy
score is claimed; the retained latest external first-attempt result stays 0/12.
