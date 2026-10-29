# GenLayer Portal submission draft — do not submit automatically

Category: Builder → Intelligent Contracts (Smart Contracts)
Points range on the form: 0–500
Evidence URL: https://github.com/jackspierrow/genlayer-factcheck
Contribution date on the form: 29/10/2026
Weekly slots on the form at drafting time: 0 of 2 used, 2 remaining
(reset Monday 00:00 UTC). Season 2 counts a submission in the season
in which it is approved, not the season in which it is sent.

## Title (optional)

FactCheckRegistry — a reusable consensus fact-check primitive

## Description (under 1000 characters — 754 characters)

FactCheckRegistry is a standalone GenLayer Intelligent Contract for
verifying claims against cited evidence. A claim is submitted with a
public evidence URL and an optional independent corroborating URL.
Verification is run under consensus: validators independently render
the evidence pages, extract a strict JSON verdict (supported, refuted
or insufficient) with a rationale, and must agree on that exact JSON
through gl.eq_principle.strict_eq before the claim state changes. A
decided claim can be disputed with a reason and re-verified, keeping
its previous status and dispute reason on record. The repo includes
the contract, a README explaining its purpose and consensus design,
and unit tests for validation, verdict parsing and the state machine.

## What the reviewer should check

- `contracts/factcheck_registry.py` — the contract itself.
- `README.md` — purpose, consensus design, state machine, limits.
- `tests/test_factcheck_registry.py` — unit tests (run:
  `python -m unittest discover -s tests -v`).
- Honest scope note: unit tests do not test consensus itself; that
  step needs GenLayer's own tooling / a local node before production use.

## Submission step (manual)

This draft is only preparation. The portal submission itself must be
made from the wallet/account that owns the portal profile, by pressing
"Kirim Kontribusi" in the portal and pasting the title, description
and evidence URL above.
