# Owner approval source

Only ciurlaro may update this protected branch, including administrators.
Force pushes and deletion are disabled. This is explicit sole-owner approval,
not a requirement for a second GitHub pull-request reviewer.

`approvals.json` authorizes exact reviewed verifier commits and retained original
qualification artifacts. Keep previously approved compatible versions when
advancing the active verifier. A qualification or cache cannot nominate code.
Original caller/product commits must come from authenticated original evidence;
the manifest intentionally supplies no replacement current or historical source.

`resolve.py` runs only from this native protected source. It freshly validates
all owner-only protection settings, its own immutable Git bytes, the manifest,
and a stable ref before returning an approved identity. Hosted execution needs
the repository-scoped, fine-grained `REUSE_AUTHORITY_READ_TOKEN` with
Administration: read and Contents: read. Never give it a writer token or cache it.

`consumer.py` freshly resolves that approval for each operation. The reusable
job binds GitHub's native `job.workflow_sha`; a composite action checks its
executing files against the independently protected source. Current receipt,
object, provenance, dependency and semantic checks run unchanged from approved
C9 bytes. Four control-only callers are compiled before execution and archived;
every other production control must already match C9. The current product HEAD
and all product inventories remain the actual consumer's.

Historical qualification source is derived from native verified SLSA, then the
unchanged production verifier repeats full source-pinned admission. Historical
aggregate Git identity comes from the authenticated receipt. The retained
qualification and SHA-addressed bodies are never rewritten. Missing authority
credentials or incompatible production controls fail closed. Unsupported native
platforms retain their existing mandatory cold authentication path.

The protected warm proof restores existing cache bodies only; it neither saves a
new cache generation nor issues new qualifications. Future genuine verifier
changes require explicit owner approval and fresh compatible original evidence.
This branch owns zero product phases and starts no SDK campaign.
