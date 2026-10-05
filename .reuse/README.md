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

Consumer wiring and the unchanged C9 execution snapshot remain pending until
that hosted read credential exists. This branch produces no product evidence.
