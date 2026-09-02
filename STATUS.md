# STATUS

## Active — Specialist composition and durable synthetic twin — issue #13

GitHub issue: https://github.com/advatar/OpenBody/issues/13
Branch: `feat/13-cognitive-health-demo`

- [ ] Compose exact specialist outputs only after descriptor, receipt, evidence, scope and horizon validation.
- [x] Add durable reference storage with unchanged canonical JSON/digest semantics.
- [ ] Support the exact post-meal-walk fixture and intentional fail-closed negative case.
- [ ] Emit a minimized clinical assertion reference and add restart tests.

Boundary: synthetic demonstration only. No clinical validation claim, raw personal data disclosure, authority bypass, or production-security claim.

Implementation progress (2026-09-02): the shared event ABI is pinned. The reference twin now has an atomic, commitment-checked durable store with restart/tamper tests and a Kubernetes StatefulSet/PVC entrypoint. Specialist-output composition and minimized clinical assertion emission remain open.
