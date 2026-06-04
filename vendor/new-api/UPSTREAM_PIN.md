# MedHarness vendor/new-api upstream pin

## Source

- Upstream repo: `https://github.com/QuantumNous/new-api.git`
- Requested tag: `v1.0.0-rc.10`
- Maintainer-provided pin object: `de83ea2f11fb21726b13e54f01190668eed2e594`
- Resolved source commit: `74985fa877b4a85decdf31044b2435cf688af395`
- Import method: `git subtree add --prefix vendor/new-api https://github.com/QuantumNous/new-api.git de83ea2f11fb21726b13e54f01190668eed2e594 --squash`
- Local subtree merge: `73d9d97eb41a277f29bf7083369c7cfff8d1b1d5`
- Import date: 2026-05-31

`v1.0.0-rc.10` is an annotated tag object at `de83ea2f11fb21726b13e54f01190668eed2e594`; GitHub resolves it to source commit `74985fa877b4a85decdf31044b2435cf688af395`. Both are recorded here so future subtree pulls can verify the exact object and source tree.

## Authorization And License Accounting

- B6 status: new-api full authorization received on 2026-05-31.
- Upstream license material retained in this subtree: `LICENSE`, `NOTICE`, `THIRD-PARTY-LICENSES.md`.
- SBOM accounting input: this pin file plus upstream `THIRD-PARTY-LICENSES.md`.
- Full SBOM command when `syft` is available:

```bash
syft dir:vendor/new-api -o cyclonedx-json > vendor/new-api/new-api.cyclonedx.json
```

## MedHarness Fork Guardrails

- Keep the subtree rebase-friendly: prefer feature flags and route guards over physical deletion.
- Resale surfaces are disabled by default via `MEDHARNESS_DISABLE_RESALE_SURFACE=true`.
- The route guard must keep self-service registration, payment, subscription, redemption, wallet, and social-login surfaces unreachable unless a maintainer explicitly disables that guard for upstream debugging.
