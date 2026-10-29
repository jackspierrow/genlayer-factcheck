"""Unit tests for FactCheckRegistry that run without a GenLayer node.

The contract imports ``genlayer``, which is only available inside a
GenLayer runtime. These tests therefore install a minimal stub for that
module first: ``gl.Contract`` is a plain class, ``@gl.public.write`` /
``@gl.public.view`` are identity decorators, ``TreeMap`` is a dict, and
``gl.message.sender_address`` is a fixed test address. The tests cover
only the parts that do not need consensus: submission validation, the
state machine, dispute handling, and verdict parsing. Consensus itself
(``gl.eq_principle.strict_eq`` over nondeterministic web data) must be
exercised with GenLayer's own test tooling; see README.md.

Run: python -m unittest discover -s tests -v
"""

import sys
import types
import unittest
from pathlib import Path

# --- Minimal genlayer stub (see module docstring) -----------------------
genlayer = types.ModuleType("genlayer")


class _Address:
    def __init__(self, hex_value):
        self._hex = hex_value

    @property
    def as_hex(self):
        return self._hex


class _Message:
    sender_address = _Address("0x0000000000000000000000000000000000000001")


class _Public:
    @staticmethod
    def write(fn):
        return fn

    @staticmethod
    def view(fn):
        return fn


class _Gl:
    Contract = object
    public = _Public()
    message = _Message()


genlayer.gl = _Gl()
genlayer.allow_storage = lambda cls: cls
genlayer.TreeMap = dict
genlayer.Address = _Address
genlayer.u256 = int
sys.modules["genlayer"] = genlayer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.factcheck_registry import (  # noqa: E402
    FactCheckRegistry,
    _parse_verdict,
    _require_http_url,
)


def _registry():
    registry = FactCheckRegistry.__new__(FactCheckRegistry)
    registry.claims = {}
    registry.next_claim_id = 0
    return registry


class TestValidation(unittest.TestCase):
    def test_rejects_non_http_evidence(self):
        with self.assertRaises(Exception):
            _require_http_url("ftp://example.com/x", "evidence_url")
        with self.assertRaises(Exception):
            _require_http_url("", "evidence_url")

    def test_parse_verdict_accepts_closed_values(self):
        self.assertEqual(
            _parse_verdict('{"verdict": "supported", "rationale": "Page says so."}'),
            {"verdict": "supported", "rationale": "Page says so."},
        )

    def test_parse_verdict_rejects_open_values_and_empty_rationale(self):
        with self.assertRaises(Exception):
            _parse_verdict('{"verdict": "maybe", "rationale": "x"}')
        with self.assertRaises(Exception):
            _parse_verdict('{"verdict": "supported", "rationale": "  "}')
        with self.assertRaises(Exception):
            _parse_verdict("not json")


class TestStateMachine(unittest.TestCase):
    def test_submit_verify_dispute_reverify(self):
        registry = _registry()
        claim_id = registry.submit_claim(
            "The city library opens on Sundays.",
            "https://example.com/library-hours",
            "https://example.com/library-news",
        )
        self.assertEqual(claim_id, "claim_0")
        self.assertEqual(registry.get_claim(claim_id)["status"], "submitted")

        # Bypass consensus in unit tests: stub the evidence check.
        registry._verify_evidence = lambda *args: {
            "verdict": "supported",
            "rationale": "Both pages list Sunday opening hours.",
        }
        self.assertEqual(registry.verify_claim(claim_id), "verified")

        # A decided claim cannot be verified again without a dispute.
        with self.assertRaises(Exception):
            registry.verify_claim(claim_id)

        registry.dispute_claim(claim_id, "New timetable page contradicts this.")
        claim = registry.get_claim(claim_id)
        self.assertEqual(claim["status"], "disputed")
        self.assertEqual(claim["previous_status"], "verified")

        registry._verify_evidence = lambda *args: {
            "verdict": "refuted",
            "rationale": "The new page says Sundays are closed.",
        }
        self.assertEqual(registry.verify_claim(claim_id), "refuted")

    def test_submit_rejects_bad_input(self):
        registry = _registry()
        with self.assertRaises(Exception):
            registry.submit_claim("", "https://example.com/x")
        with self.assertRaises(Exception):
            registry.submit_claim("A claim", "not-a-url")
        with self.assertRaises(Exception):
            registry.submit_claim("A claim", "https://example.com/x")
            registry.dispute_claim("claim_0", "x")

    def test_stats_count_by_status(self):
        registry = _registry()
        registry.submit_claim("One", "https://example.com/1")
        registry.submit_claim("Two", "https://example.com/2")
        registry._verify_evidence = lambda *args: {
            "verdict": "insufficient",
            "rationale": "Pages do not cover this.",
        }
        registry.verify_claim("claim_0")
        self.assertEqual(
            registry.get_stats(),
            {
                "total": 2,
                "submitted": 1,
                "verified": 0,
                "refuted": 0,
                "unverified": 1,
                "disputed": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
