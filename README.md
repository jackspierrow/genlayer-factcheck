# genlayer-factcheck

A reusable GenLayer Intelligent Contract primitive: **FactCheckRegistry**.

Submit a claim with public evidence URLs, verify it under GenLayer
consensus, and dispute a decided claim so it can be re-verified. The
contract is standalone — no frontend, no token, no off-chain backend —
so other contracts and apps can read a claim's final status and rationale,
or build dispute and reputation flows on top of it.

## Why this is not a thin LLM wrapper

A naive fact-checker would call an LLM once and store whatever it says.
FactCheckRegistry does the opposite:

1. **Evidence first.** `submit_claim` requires at least one public
   `http(s)` evidence URL and accepts a second, independent corroborating
   URL. Empty claims, non-HTTP URLs and over-long inputs are rejected
   before any state is written.
2. **Validators fetch the pages themselves.** In `verify_claim`, each
   validator independently renders the evidence URLs with
   `gl.nondet.web.render` and asks an LLM to extract a verdict *from the
   rendered pages only*, in a strict JSON document
   (`verdict`, `rationale`).
3. **Consensus, not one answer.** The extracted JSON is passed through
   `gl.eq_principle.strict_eq`. Every validator must agree on the exact
   JSON document before the contract accepts it. A verdict that differs
   between validators, or that cannot be parsed, fails instead of silently
   picking one validator's answer.
4. **Closed verdicts, explained decisions.** The only verdicts are
   `supported`, `refuted` and `insufficient`, and a decision is never
   stored without a non-empty rationale (bounded to 1000 characters).
   They map to the claim states `verified`, `refuted` and `unverified`.
5. **An auditable state machine.** A decided claim cannot be verified
   again without first being disputed with a reason. Disputes keep
   `previous_status` and `dispute_reason` on the record, so the history
   of a claim stays readable.

```
submitted  -> verified | refuted | unverified   (verify_claim)
verified | refuted | unverified -> disputed     (dispute_claim)
disputed  -> verified | refuted | unverified     (verify_claim again)
```

## Contract

File: `contracts/factcheck_registry.py` (GenLayer Python contract).

| Method | Type | What it does |
| --- | --- | --- |
| `submit_claim(claim_text, evidence_url, corroborating_url="")` | write | Validates input, stores a claim as `submitted`, returns its id (`claim_0`, `claim_1`, …). |
| `verify_claim(claim_id)` | write | Runs consensus verification, stores the verdict and rationale, returns the new status. Only `submitted` and `disputed` claims can be verified. |
| `dispute_claim(claim_id, reason)` | write | Moves a decided claim to `disputed`, keeping the previous status and the reason. |
| `get_claim(claim_id)` | view | Returns the full claim record. |
| `get_all_claims()` | view | Returns all claim records. |
| `get_stats()` | view | Returns counts per status. |

State per claim: `id`, `submitter`, `claim_text`, `evidence_url`,
`corroborating_url`, `status`, `verdict`, `rationale`,
`previous_status`, `dispute_reason`.

## Example flow

```python
# 1. Submit (any wallet)
claim_id = submit_claim(
    "The city library opens on Sundays.",
    "https://example.com/library-hours",
    "https://example.com/library-news",
)
# -> "claim_0", status "submitted"

# 2. Verify (any wallet triggers consensus verification)
verify_claim(claim_id)
# -> "verified" | "refuted" | "unverified", with a stored rationale

# 3. Dispute, then re-verify if new evidence appears
dispute_claim(claim_id, "A new timetable page contradicts this.")
verify_claim(claim_id)
```

## Tests

Unit tests run without a GenLayer node. They stub the `genlayer`
module (see the header of the test file) and cover submission
validation, verdict parsing, the state machine, dispute handling and
statistics:

```bash
python -m unittest discover -s tests -v
# Ran 6 tests — OK
```

Consensus itself (`strict_eq` over nondeterministic web data) cannot be
meaningfully tested with a stub. It must be exercised with GenLayer's own
tooling — for example, by deploying the contract with GenLayer Studio /
`genlayer-cli` and running its integration tests against a local
GenLayer node — before any production use. The unit tests above are
explicitly not a substitute for that step.

## Limitations

- Evidence pages must be publicly fetchable by validators; paywalled or
  bot-blocked pages will fail verification rather than produce a verdict.
- The LLM is instructed to use only the rendered evidence pages, not its
  own knowledge, but a page that itself contains a false claim can still
  produce a `supported` verdict — the contract verifies claims *against
  the cited evidence*, it does not establish ground truth.
- Rationale and claim text are bounded (1000 characters each) to keep
  on-chain state small.
