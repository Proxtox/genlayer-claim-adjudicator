# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
import json
import typing


@allow_storage
@dataclass
class Claim:
    """Structured record for a single contested claim."""
    claim_id: str
    claimant: Address
    claim_text: str                 # Natural-language description of the claim
    criteria: str                   # Explicit adjudication standard (what must be true)
    evidence_urls: DynArray[str]    # Fixed + caller-supplied authoritative sources
    status: str                     # "open" | "resolved" | "rejected"
    verdict: str                    # "true" | "false" | "inconclusive" | ""
    reasoning: str
    confidence: str                 # "high" | "medium" | "low" | ""
    created_at: str
    resolved_at: str


class ClaimAdjudicator(gl.Contract):
    """
    Evidence-Based Contested Claim Adjudicator
    ==========================================

    A reusable GenLayer primitive for resolving genuinely contested real-world
    claims.  A claim is only accepted when independent validators, each fetching
    live web evidence and applying the same explicit criteria, reach consensus
    under the Equivalence Principle.

    Why this belongs on GenLayer
    ----------------------------
    - The claim is contested: a false "true" benefits the claimant; a false
      "false" benefits any counter-party (insurer, counterparty, protocol).
    - Evidence is fetched live inside the consensus round, never trusted from
      a single party description.
    - Decision fields (verdict + confidence) are forced into a canonical shape
      so validators can agree on meaning even when prose reasoning differs.

    Typical use cases
    -----------------
    - Parametric insurance triggers (flight delay, weather threshold, outage)
    - Service-level / deliverable verification
    - Open-source bounty completion checks
    - Event-outcome settlement (sports, elections, market events)
    - Protocol violation or incident confirmation
    """

    claims: TreeMap[str, Claim]
    claim_counter: u256
    owner: Address

    def __init__(self):
        self.claim_counter = u256(0)
        self.owner = gl.message.sender_address

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    @gl.public.write
    def open_claim(
        self,
        claim_text: str,
        criteria: str,
        evidence_urls: list[str],
    ) -> str:
        """
        Open a new contested claim.

        Parameters
        ----------
        claim_text : Natural language statement of the claim
                     e.g. "Flight AA123 on 2026-09-20 was delayed more than 3 hours"
        criteria   : Explicit standard the evidence must satisfy for a "true" verdict.
                     e.g. "Official flight status shows arrival delay >= 180 minutes"
        evidence_urls : List of authoritative URLs (airline status page, FlightAware,
                        official weather API, etc.).  At least one must be provided.

        Returns the generated claim_id.
        """
        if not claim_text or not claim_text.strip():
            raise Exception("claim_text cannot be empty")
        if not criteria or not criteria.strip():
            raise Exception("criteria cannot be empty")
        if not evidence_urls or len(evidence_urls) == 0:
            raise Exception("at least one evidence_url is required")

        self.claim_counter += u256(1)
        claim_id = f"claim-{int(self.claim_counter)}"

        urls = DynArray[str]()
        for u in evidence_urls:
            urls.append(str(u).strip())

        new_claim = Claim(
            claim_id=claim_id,
            claimant=gl.message.sender_address,
            claim_text=claim_text.strip(),
            criteria=criteria.strip(),
            evidence_urls=urls,
            status="open",
            verdict="",
            reasoning="",
            confidence="",
            created_at=str(gl.block.timestamp) if hasattr(gl, "block") else "",
            resolved_at="",
        )
        self.claims[claim_id] = new_claim
        return claim_id

    @gl.public.write
    def adjudicate(self, claim_id: str) -> typing.Any:
        """
        Resolve an open claim by fetching live evidence and reaching consensus.

        Consensus design
        ----------------
        1. Every validator independently fetches the same evidence URLs.
        2. Leader produces a structured JSON verdict.
        3. Validators re-run the same task and accept only when the decision
           fields (verdict + confidence) match under the Equivalence Principle
           (prompt_comparative on the canonical decision object).

        This guarantees that a false verdict cannot be forced by a single
        model or a single evidence snapshot.
        """
        if claim_id not in self.claims:
            raise Exception(f"claim {claim_id} does not exist")

        claim = self.claims[claim_id]
        if claim.status != "open":
            raise Exception(f"claim {claim_id} is already {claim.status}")

        # Capture state needed inside the non-deterministic block
        claim_text = claim.claim_text
        criteria = claim.criteria
        urls = [str(u) for u in claim.evidence_urls]

        def gather_and_judge() -> str:
            """
            Non-deterministic core: fetch evidence, then ask the LLM for a
            strictly structured decision.  Return a canonical JSON string so
            that prompt_comparative can compare decision fields.
            """
            evidence_blobs = []
            for url in urls:
                try:
                    resp = gl.nondet.web.get(url)
                    body = resp.body.decode("utf-8") if hasattr(resp, "body") else str(resp)
                    # Truncate to keep context manageable
                    evidence_blobs.append(f"SOURCE: {url}\n{body[:8000]}")
                except Exception as e:
                    evidence_blobs.append(f"SOURCE: {url}\n[FETCH FAILED: {str(e)}]")

            combined_evidence = "\n\n---\n\n".join(evidence_blobs)

            prompt = f"""You are an impartial adjudicator.  Decide whether the following claim is supported by the live evidence.

CLAIM:
{claim_text}

ADJUDICATION CRITERIA (the claim is TRUE only if this is satisfied):
{criteria}

LIVE EVIDENCE (fetched from the listed sources):
{combined_evidence}

Respond with ONLY a valid JSON object, no markdown, no extra text:
{{
  "verdict": "true" | "false" | "inconclusive",
  "confidence": "high" | "medium" | "low",
  "reasoning": "one or two concise sentences citing the decisive evidence"
}}

Rules:
- "true" only when the evidence clearly satisfies the criteria.
- "false" when the evidence clearly contradicts the criteria.
- "inconclusive" when evidence is missing, conflicting, or insufficient.
- Prefer "inconclusive" over guessing.
"""

            raw = gl.nondet.exec_prompt(prompt)
            # Strip common markdown fences
            cleaned = raw.replace("```json", "").replace("```", "").strip()
            # Force a parseable shape; raise if invalid so the round fails cleanly
            parsed = json.loads(cleaned)
            # Canonical serialization of the decision fields only
            decision = {
                "verdict": str(parsed.get("verdict", "inconclusive")).lower(),
                "confidence": str(parsed.get("confidence", "low")).lower(),
                "reasoning": str(parsed.get("reasoning", ""))[:500],
            }
            if decision["verdict"] not in ("true", "false", "inconclusive"):
                decision["verdict"] = "inconclusive"
            if decision["confidence"] not in ("high", "medium", "low"):
                decision["confidence"] = "low"
            return json.dumps(decision, sort_keys=True)

        # Comparative equivalence: every validator re-fetches evidence and
        # produces its own decision object; they accept only when the
        # decision fields are equivalent under the stated principle.
        result_str = gl.eq_principle.prompt_comparative(
            gather_and_judge,
            principle=(
                "The 'verdict' field must be identical. "
                "The 'confidence' field must be identical or differ by at most one level "
                "(high↔medium or medium↔low). "
                "Reasoning may differ in wording but must support the same verdict."
            ),
        )

        result = json.loads(result_str)

        # Persist the consensus outcome
        claim.status = "resolved"
        claim.verdict = result["verdict"]
        claim.confidence = result["confidence"]
        claim.reasoning = result.get("reasoning", "")
        claim.resolved_at = str(gl.block.timestamp) if hasattr(gl, "block") else ""
        self.claims[claim_id] = claim

        return {
            "claim_id": claim_id,
            "verdict": claim.verdict,
            "confidence": claim.confidence,
            "reasoning": claim.reasoning,
            "status": claim.status,
        }

    # ------------------------------------------------------------------
    # View methods
    # ------------------------------------------------------------------

    @gl.public.view
    def get_claim(self, claim_id: str) -> dict:
        """Return full details of a single claim."""
        if claim_id not in self.claims:
            return {"error": f"claim {claim_id} not found"}
        c = self.claims[claim_id]
        return {
            "claim_id": c.claim_id,
            "claimant": str(c.claimant),
            "claim_text": c.claim_text,
            "criteria": c.criteria,
            "evidence_urls": [str(u) for u in c.evidence_urls],
            "status": c.status,
            "verdict": c.verdict,
            "confidence": c.confidence,
            "reasoning": c.reasoning,
            "created_at": c.created_at,
            "resolved_at": c.resolved_at,
        }

    @gl.public.view
    def list_claims(self) -> list:
        """Return a summary of all claims (id, status, verdict)."""
        out = []
        for cid, c in self.claims.items():
            out.append({
                "claim_id": cid,
                "status": c.status,
                "verdict": c.verdict,
                "claimant": str(c.claimant),
            })
        return out

    @gl.public.view
    def get_claim_count(self) -> int:
        return int(self.claim_counter)
