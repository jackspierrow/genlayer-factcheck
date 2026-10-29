# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
FactCheckRegistry: a reusable GenLayer Intelligent Contract primitive.

A claim is submitted with at least one public evidence URL and, ideally,
a second, independent corroborating URL. Anyone may then trigger
verification. Verification is not a single LLM call whose output is trusted:
validators fetch the evidence pages themselves (nondeterministic web data),
ask an LLM to extract a strict JSON verdict from that fetched content, and
then reach consensus on that JSON through GenLayer's equivalence principle
(``gl.eq_principle.strict_eq``). Only the consensus verdict may change the
claim's state. A decided claim can be disputed with a reason, which returns
it to a disputable state so it can be re-verified against new evidence.

This is a standalone contract primitive, not a full application: it has no
frontend, no token, and no off-chain backend. Other contracts and apps can
read a claim's final status and rationale, or build their own dispute and
reputation flows on top of it.

State machine
-------------
submitted  -> verified | refuted | unverified   (via verify_claim)
verified | refuted | unverified -> disputed   (via dispute_claim)
disputed  -> verified | refuted | unverified   (via verify_claim again)

A claim that has already been decided cannot be submitted twice under the
same id, and a claim cannot be verified while it is already in a final
state without first being disputed. That keeps the audit trail readable:
``previous_status`` and ``dispute_reason`` are kept on the claim record.
"""

import json
from dataclasses import dataclass

from genlayer import *


def _require_http_url(url: str, field: str) -> None:
    """Reject empty, non-HTTP(S) and obviously malformed evidence URLs.

    This is a format guard only. It does not judge whether a page is true;
    that judgement happens under consensus in ``_verify_evidence``.
    """
    if not isinstance(url, str) or not url.strip():
        raise Exception(f"{field} must be a non-empty URL")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise Exception(f"{field} must start with http:// or https://")
    if len(url) > 2048:
        raise Exception(f"{field} is too long")


def _parse_verdict(raw: str) -> dict:
    """Parse and validate a consensus verdict JSON document.

    Pure function, so it can be unit-tested without a GenLayer node.
    ``verdict`` must be one of the three closed values; ``rationale`` must
    be present and non-empty so a decision is never stored unexplained.
    """
    try:
        verdict = json.loads(raw)
    except Exception as exc:
        raise Exception(f"Verdict is not valid JSON: {exc}") from exc
    if not isinstance(verdict, dict):
        raise Exception("Verdict must be a JSON object")
    if verdict.get("verdict") not in ("supported", "refuted", "insufficient"):
        raise Exception("Verdict must be supported, refuted or insufficient")
    rationale = verdict.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise Exception("Verdict rationale must be a non-empty string")
    return {
        "verdict": verdict["verdict"],
        # Keep the stored rationale bounded so one claim cannot bloat state.
        "rationale": rationale.strip()[:1000],
    }


@allow_storage
@dataclass
class Claim:
    id: str
    submitter: str
    claim_text: str
    evidence_url: str
    corroborating_url: str
    status: str
    verdict: str
    rationale: str
    previous_status: str
    dispute_reason: str


class FactCheckRegistry(gl.Contract):
    claims: TreeMap[str, Claim]
    next_claim_id: u256

    def __init__(self):
        self.next_claim_id = 0

    def _verify_evidence(
        self, claim_text: str, evidence_url: str, corroborating_url: str
    ) -> dict:
        """Run consensus verification over the claim's evidence pages.

        Each validator independently renders the evidence URLs, asks an LLM
        to extract a verdict from the rendered content only (never from the
        claim text alone), and then ``strict_eq`` requires every validator
        to agree on the exact JSON document before the contract accepts it.
        A verdict that differs between validators, or that cannot be parsed,
        therefore fails the transaction instead of silently picking one
        validator's answer.
        """

        def get_verdict() -> str:
            pages = []
            for label, url in (
                ("primary evidence", evidence_url),
                ("corroborating evidence", corroborating_url),
            ):
                if url:
                    pages.append(
                        f"{label} ({url}):\n"
                        f"{gl.nondet.web.render(url, mode='text')}"
                    )
            task = f"""
Claim to check:
{claim_text}

Evidence pages (use only these pages, not your own knowledge):
{chr(10).join(pages)}

Respond in JSON only, with exactly these fields:
{{
    "verdict": "supported" | "refuted" | "insufficient",
    "rationale": str
}}
- "supported": the evidence pages directly support the claim.
- "refuted": the evidence pages directly contradict the claim.
- "insufficient": the pages do not contain enough to support or refute it.
- "rationale": one or two sentences quoting what the pages actually say.
Do not include any other words, formatting or explanation outside the JSON.
            """
            result = gl.nondet.exec_prompt(task, response_format="json")
            return json.dumps(result, sort_keys=True)

        return _parse_verdict(gl.eq_principle.strict_eq(get_verdict))

    @gl.public.write
    def submit_claim(
        self, claim_text: str, evidence_url: str, corroborating_url: str = ""
    ) -> str:
        if not isinstance(claim_text, str) or not claim_text.strip():
            raise Exception("claim_text must be a non-empty string")
        if len(claim_text) > 1000:
            raise Exception("claim_text is too long (max 1000 characters)")
        _require_http_url(evidence_url, "evidence_url")
        if corroborating_url:
            _require_http_url(corroborating_url, "corroborating_url")

        submitter = gl.message.sender_address.as_hex
        claim_id = f"claim_{int(self.next_claim_id)}"
        if claim_id in self.claims:
            raise Exception("Claim id already exists")

        self.claims[claim_id] = Claim(
            id=claim_id,
            submitter=submitter,
            claim_text=claim_text.strip(),
            evidence_url=evidence_url.strip(),
            corroborating_url=corroborating_url.strip(),
            status="submitted",
            verdict="",
            rationale="",
            previous_status="",
            dispute_reason="",
        )
        self.next_claim_id = int(self.next_claim_id) + 1
        return claim_id

    @gl.public.write
    def verify_claim(self, claim_id: str) -> str:
        if claim_id not in self.claims:
            raise Exception("Claim does not exist")
        claim = self.claims[claim_id]
        if claim.status not in ("submitted", "disputed"):
            raise Exception(
                "Claim must be submitted or disputed before verification; "
                "dispute a decided claim first"
            )

        verdict = self._verify_evidence(
            claim.claim_text, claim.evidence_url, claim.corroborating_url
        )
        claim.previous_status = claim.status
        claim.verdict = verdict["verdict"]
        claim.rationale = verdict["rationale"]
        claim.status = {
            "supported": "verified",
            "refuted": "refuted",
            "insufficient": "unverified",
        }[verdict["verdict"]]
        self.claims[claim_id] = claim
        return claim.status

    @gl.public.write
    def dispute_claim(self, claim_id: str, reason: str) -> None:
        if claim_id not in self.claims:
            raise Exception("Claim does not exist")
        if not isinstance(reason, str) or not reason.strip():
            raise Exception("dispute reason must be a non-empty string")
        claim = self.claims[claim_id]
        if claim.status not in ("verified", "refuted", "unverified"):
            raise Exception("Only a decided claim can be disputed")
        claim.previous_status = claim.status
        claim.status = "disputed"
        claim.dispute_reason = reason.strip()[:1000]
        self.claims[claim_id] = claim

    @gl.public.view
    def get_claim(self, claim_id: str) -> dict:
        if claim_id not in self.claims:
            raise Exception("Claim does not exist")
        claim = self.claims[claim_id]
        return {
            "id": claim.id,
            "submitter": claim.submitter,
            "claim_text": claim.claim_text,
            "evidence_url": claim.evidence_url,
            "corroborating_url": claim.corroborating_url,
            "status": claim.status,
            "verdict": claim.verdict,
            "rationale": claim.rationale,
            "previous_status": claim.previous_status,
            "dispute_reason": claim.dispute_reason,
        }

    @gl.public.view
    def get_all_claims(self) -> dict:
        return {claim_id: self.get_claim(claim_id) for claim_id in self.claims}

    @gl.public.view
    def get_stats(self) -> dict:
        stats = {
            "total": 0,
            "submitted": 0,
            "verified": 0,
            "refuted": 0,
            "unverified": 0,
            "disputed": 0,
        }
        for claim in self.claims.values():
            stats["total"] += 1
            if claim.status in stats:
                stats[claim.status] += 1
        return stats
