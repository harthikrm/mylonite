# External timestamps of the C2 commitment

The owner approved this on 2026-11-01 ("Approve all three"), as one of the three outside requests
for C2 and C4. Only a digest left the machine.

- **What is stamped.** `../c2_commitment.json` as committed in `50fe826` (C2). Its SHA-256 is
  `af7e6fafa41d4f7f2ccaa7580ac66898e49a8a1cc0a0cdfb442c88c7d65aa142`; the raw 32 bytes are in
  `c2_commitment.json.sha256.bin`. That file names round R = 6605131, scheduled
  2026-11-02T02:02:30Z, and holds the salted commitment to the sealed bases.
- **RFC 3161, FreeTSA** (`https://freetsa.org/tsr`):
  - The request is `c2_commitment.json.tsq`, made with
    `openssl ts -query -data ../c2_commitment.json -sha256 -no_nonce -cert`. The reply is
    `c2_commitment.json.tsr`.
  - FACT: status Granted; signed time **2026-11-01 19:57:54 UTC**. That is 6 h 4 min 36 s
    before round 6605131 is scheduled.
  - FACT: the token's message imprint equals the digest above. Its signature verifies against
    the certificates embedded in the token (`openssl ts -verify … -partial_chain`, "OK").
  - **Not yet done:** verification up to FreeTSA's published root. That needs FreeTSA's CA file,
    which is a download and needs approval, or it can be done by anyone at publication.
- **OpenTimestamps.**
  - The raw digest was POSTed to `/digest` on the four default calendars:
    - `a.pool.opentimestamps.org`
    - `b.pool.opentimestamps.org`
    - `a.pool.eternitywall.com`
    - `ots.btc.catallaxy.com`
  - All returned HTTP 200, at 19:57:44 UTC or a few seconds before. Each response
    (`ots-<calendar>.bin`) is a serialized timestamp for the digest, ending in a **pending**
    attestation (alice, bob, finney and catallaxy).
  - These are raw calendar responses, not assembled `.ots` files. The digest was not blinded
    with a nonce, as the `ots` client would do. It is the SHA-256 of a file that holds only
    another salted digest, so nothing guessable is exposed.
  - **Pending:** the upgrade to Bitcoin block attestations, and verification. Both need the
    `ots` client, which is a PyPI download and needs approval, or a hand-written parser.
- **Ordering.** The RFC 3161 time precedes round R's scheduled time by more than 6 hours.
  Under `HELDOUT_PROTOCOL.md`, that makes the C2 → R ordering externally verified, subject to
  the root-chain check above. A pending OTS calendar receipt only trusts the calendar until it
  is upgraded.
