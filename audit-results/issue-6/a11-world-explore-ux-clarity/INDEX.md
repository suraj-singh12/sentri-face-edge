# A-11 World Explore UX clarity evidence index

- [Runtime verification](runtime-verification.md) — authoritative fixture states, API comparisons, source mechanics, limitations.
- [Visual proposal](visual-proposal.md) — before/after evidence and the proposed minimal copy/control refinement.
- [Machine-readable verification](data/a11-authoritative-verification.json)
- [High Alpha focused API example](data/api-person-high-alpha-th2.json)
- [Type Alpha default evidence-selection API example](data/api-person-type-alpha-default-co.json)
- [Type Alpha with manual evidence API example](data/api-person-type-alpha-with-manual.json)

## Screenshot sets

### Runtime before

- [Zero relationships](screenshots/before/zero-no-relationships.png)
- [Below-threshold isolated](screenshots/before/below-threshold-isolated.png)
- [Mixed-strength Person](screenshots/before/mixed-strength-person.png)
- [Evidence-type excluded](screenshots/before/type-excluded-default.png)
- [Manual evidence included control](screenshots/before/manual-evidence-included.png)
- [Qualifying Person](screenshots/before/qualifying-person.png)
- [Cluster with weaker links on](screenshots/before/cluster-weaker-on.png)
- [Cluster with weaker links off](screenshots/before/cluster-weaker-off.png)

### Visual proposal after

- [Zero relationships](screenshots/after/zero-no-relationships.png)
- [Below-threshold isolated](screenshots/after/below-threshold-isolated.png)
- [Mixed-strength Person](screenshots/after/mixed-strength-person.png)
- [Evidence-type excluded](screenshots/after/type-excluded.png)
- [Weaker links in view](screenshots/after/weaker-links-in-view.png)

Product baseline: `v2-hardening-followups` at `613b352f0d68580356345aea8401ab52dfaf9797`. Evidence-only proposal; no implementation.
