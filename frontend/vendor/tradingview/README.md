# TradingView Advanced Charts — vendored

The library lives in this repository rather than being fetched at build time
(ADR 0004). The arrangement it replaces pulled a tarball from a private URL with
a token, which made every build — CI, a new contributor's first clone, a
rebuild two years from now — depend on a host and a credential that may not be
there.

## What is where

| Path | What | How it is stored |
|---|---|---|
| `frontend/vendor/tradingview/*.d.ts` | Type definitions | Plain git — TypeScript reads them on every `tsc`, and an unsmudged LFS pointer would break compilation |
| `frontend/public/charting_library/` | Runtime, served as static assets | Git LFS — **not yet committed, see below** |

## The runtime is not in the repository yet

Pushing it failed:

```
batch response: This repository exceeded its LFS budget.
The account responsible for the budget should increase it to restore access.
```

That is an account setting, not a code problem, and it is not something a commit
can work around. Until it is resolved the application code is complete and the
chart will not render — `loadLibrary.ts` reports the missing asset rather than
showing an empty rectangle, because "no data" and "the library is absent" send
whoever is looking in completely different directions.

Three ways forward, in the order I would take them:

1. **Raise the LFS budget** (GitHub → Settings → Billing). `.gitattributes`
   already has the tracking rules, so `git add frontend/public/charting_library`
   then does the right thing.
2. **Commit as plain git.** Works today, costs ~27 MB in history permanently for
   every clone, and cannot be undone without rewriting history.
3. **Provision at deploy time** from private object storage. Keeps the repository
   small, but reintroduces exactly the external dependency ADR 0004 removed.

## Getting the files

They are the standard TradingView Advanced Charts distribution: copy
`charting_library/` from a release into `frontend/public/charting_library/`.
`loadLibrary.ts` expects `charting_library.standalone.js` at the root of that
directory and the `bundles/` folder beside it.

## Licence

TradingView's Advanced Charts licence permits use but **not public
redistribution**. Vendoring into a *private* repository is the normal
arrangement and is what this assumes.

**If `loorksy/leovee` is ever made public, this directory becomes a licence
violation.** `scripts/check_repo_visibility.sh` fails the build when the
repository reports itself public while these files are present, so the mistake
is caught by CI rather than discovered by TradingView.

## Updating

Replace the contents wholesale from a fresh TradingView release. Do not patch
files in place: the bundle names carry content hashes, and a hand-edited chunk
will be silently replaced the next time anything else is updated.
