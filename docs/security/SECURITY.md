# Security Notes

## Threat Model

The analyzed repository is attacker-controlled input. Source code, comments, README
content, project metadata, and documentation excerpts are evidence, not instructions.

## Controls

- Public GitHub URL validation rejects non-HTTPS, non-GitHub, path traversal, and embedded credentials.
- GitHub and archive clients block private and loopback SSRF targets.
- Archive extraction rejects path traversal, absolute paths, symlinks, excessive compressed size, excessive extracted size, excessive file count, and excessive path depth.
- Repository code is never imported, executed, tested, installed, or built.
- Trusted documentation retrieval uses allowlisted official Pydantic sources and cached snapshots.
- Prompt templates delimit untrusted repository and documentation text.
- LLM outputs are structured Pydantic models with call, token, timeout, and length budgets.
- Evidence validators check file existence, exact lines, bounded snippets, rule IDs, docs, package claims, risk components, prohibited claims, and output lengths.
- Secret redaction runs before logs, traces, feedback, and report rendering.
- LangSmith and Redis outages degrade observability/cache behavior without corrupting analysis.

## Local Release Scanning

Run:

```bash
uv run python scripts/security_scan.py --markdown-output docs/security/SECURITY_SCAN_RESULTS.md
uv run python scripts/generate_sbom.py --output docs/security/sbom.cdx.json
```

The local scanner is intentionally dependency-free. For production, add external CVE
and image scanners to CI.
