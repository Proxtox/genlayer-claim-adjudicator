# GenLayer Claim Adjudicator

**Standalone Intelligent Contract** for resolving genuinely contested real-world claims using live web evidence and multi-validator LLM consensus under the Equivalence Principle.

> Submission category: **Intelligent Contracts** (standalone primitive)  
> Not a hello-world, thin LLM wrapper, or one-off demo.

---

## Purpose

Traditional smart contracts cannot judge subjective or real-world questions. Oracles introduce single points of trust. GenLayer lets contracts fetch live evidence and reach agreement on judgment.

This contract is a **reusable adjudication primitive**:

- A party opens a claim with natural-language text + explicit criteria + authoritative evidence URLs.
- Anyone can trigger adjudication.
- Validators independently re-fetch the evidence, run the same judgment task, and accept the leader’s structured verdict only when decision fields match under a defined Equivalence Principle.
- The final verdict (`true` / `false` / `inconclusive`) + confidence + short reasoning are stored on-chain.

### Why the claim is contested (structural requirement)

A false “true” benefits the claimant (payout, reputation, settlement).  
A false “false” or forced “inconclusive” benefits any counter-party (insurer, counterparty, protocol treasury).  
Therefore multi-validator consensus is not decorative — it is the security mechanism.

---

## How Consensus Is Used

| Stage | What happens |
|-------|--------------|
| Evidence | Every validator calls `gl.nondet.web.get` on the same URLs inside the non-deterministic block. No party-supplied “evidence text” is trusted. |
| Judgment | Leader produces a strict JSON object: `{verdict, confidence, reasoning}`. |
| Equivalence | `gl.eq_principle.prompt_comparative` — validators re-run the full gather+judge task and accept only when `verdict` is identical and `confidence` differs by at most one level. Reasoning may vary in wording. |
| Persistence | Only after consensus succeeds is the claim marked `resolved` and the decision fields written. |

This pattern forces agreement on the **decision**, not on incidental prose, while still requiring independent evidence retrieval.

---

## State Design

```python
@allow_storage
@dataclass
class Claim:
    claim_id: str
    claimant: Address
    claim_text: str
    criteria: str
    evidence_urls: DynArray[str]
    status: str          # "open" | "resolved" | "rejected"
    verdict: str         # "true" | "false" | "inconclusive"
    reasoning: str
    confidence: str      # "high" | "medium" | "low"
    created_at: str
    resolved_at: str

claims: TreeMap[str, Claim]
claim_counter: u256
owner: Address
```

- `TreeMap` for O(log n) lookup by claim_id.
- Strong typing on every persistent field.
- Status machine prevents double-resolution.

---

## Public Interface

### `open_claim(claim_text, criteria, evidence_urls) → claim_id`

Creates a new open claim. Requires non-empty text, criteria, and at least one URL.

### `adjudicate(claim_id) → {claim_id, verdict, confidence, reasoning, status}`

Triggers the full evidence + consensus flow. Idempotent only after resolution (re-calling on a resolved claim reverts).

### Views

- `get_claim(claim_id)` – full record
- `list_claims()` – summary of all claims
- `get_claim_count()` – total opened

---

## Example Usage

```python
# 1. Open a parametric flight-delay claim
claim_id = contract.open_claim(
    claim_text="American Airlines flight AA123 on 2026-09-20 arrived more than 3 hours late",
    criteria="Official status page or FlightAware shows arrival delay >= 180 minutes relative to scheduled arrival",
    evidence_urls=[
        "https://www.flightaware.com/live/flight/AAL123",
        "https://www.aa.com/travelInformation/flights/status"
    ]
)

# 2. Later, anyone triggers adjudication
result = contract.adjudicate(claim_id)
# → {"verdict": "true", "confidence": "high", "reasoning": "...", ...}
```

Other natural use cases: weather-threshold insurance, GitHub PR bounty completion, uptime SLA breaches, supply-chain disruption confirmation, election/market event settlement.

---

## Design Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| `prompt_comparative` over `strict_eq` | LLM reasoning text will never be byte-identical; we care about the decision fields. |
| Force JSON + `sort_keys` inside the non-det block | Gives the comparative principle a stable object to compare. |
| Require caller-supplied authoritative URLs | Prevents the contract from becoming a free-form “AI decides anything” oracle. Evidence sources are part of the claim definition. |
| “inconclusive” as first-class outcome | Better to fail open than force a binary decision on weak evidence. |
| No automatic payout in this primitive | Keeps the contract focused on adjudication. Settlement can be composed on top (escrow, insurance pool, etc.). |

---

## File Layout

```
contracts/
  ClaimAdjudicator.py     # The Intelligent Contract
README.md                 # This file
docs/
  (optional future notes)
```

---

## Deployment Notes

1. Pin the GenVM runner (already present in the file header).
2. Deploy via GenLayer CLI / Studio / deploy scripts.
3. Constructor takes no arguments.
4. After deployment, call `open_claim` then `adjudicate`.

---

## Educational Value for Other Builders

- Clear separation of deterministic state machine vs non-deterministic judgment block.
- Practical example of `prompt_comparative` with an explicit principle focused on decision fields.
- Shows how to force structured output so equivalence is meaningful.
- Demonstrates a contested-claim pattern that satisfies GenLayer’s “consensus is structural” guideline.
- Ready to be extended into insurance, escrow, or bounty settlement contracts.

---

## License

MIT
