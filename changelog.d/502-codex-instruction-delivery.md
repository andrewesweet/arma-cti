### Fixed

- Codex dispatches now run a synchronous `codex debug prompt-input` preflight before a
  dispatch record or child is created. A difference between the independently read expected
  source chain and the delivered project text is `instruction_delivery_mismatch`; a preflight
  that cannot answer is `instruction_preflight_unavailable`; both are `infra_unavailable`
  refusals and start no agent work.

- The preflight and the Codex child receive a scoped 96 KiB project-document limit, while the
  current source-chain tripwire keeps the 24 KiB retirement threshold visible. The proof stores
  normalized byte counts and hashes, source paths and hashes, the launch and loader identity,
  and separate global-capture measurements without storing instruction or credential text.

- The proof establishes exact delivered text under its recorded `lf-v1` normalization plus
  independently recorded expected source identities, but it cannot distinguish two source
  chains that render byte-identical text: `LoadedAgentsMd.sources()` exists internally, and no
  bounded non-interactive command emits it.
