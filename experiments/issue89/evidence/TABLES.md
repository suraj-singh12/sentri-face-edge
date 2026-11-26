### S1 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 12} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 11, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 18 | 15 | yes |
| Sightings (sum over People) | 15 | 18 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Fir 2026-05-20→2026-05-20 f1.0; Ginkgo 2026-05-20→2026-05-20 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Kauri 2026-05-20→2026-05-20 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 15 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (16, 19, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 19 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Kauri 0.169; fir→Fir 0.603; ginkgo→Ginkgo 0.605; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Kauri 0.607; laurel→Kauri 0.113; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 2} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 3 | 2 | yes |
| Event Note selected mentions | 0 | 1 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 11, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 14 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 12 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Fir,Ginkgo,Kauri} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 13 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 10 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Fir:1; Alder:1; Ginkgo:1; Kauri:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 2 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 37 | 38 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history']; API reads differing 0/254 (+12 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S2 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 9} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 17 | 15 | yes |
| Sightings (sum over People) | 15 | 17 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-20 f2.812; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 16 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (17, 19, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 19 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.595; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 2} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 3 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 11 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 9 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 9 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch,Cedar} | {Alder,Birch} | yes |
| World explore relationships | 7 | 7 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:3; Alder:3; Birch:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 3 | 2 | yes |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 31 | 32 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history']; API reads differing 0/254 (+6 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S3 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 10} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 9, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 18 | 15 | yes |
| Sightings (sum over People) | 15 | 18 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-02-01→2026-05-25 f0.789; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-02-01→2026-04-25 f0.714; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Kauri 2026-02-01→2026-02-01 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 15 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (16, 19, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 19 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Kauri 0.216; fir→Dogwood 0.141; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Kauri 0.603; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 10, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 12 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 11 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Iris,Juniper,Kauri} {Hazel,Juniper Two} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 11 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 9 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 3 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 33 | 34 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history']; API reads differing 0/254 (+0 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S4 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 12} | {'ACTIVE': 12} | {'ACTIVE': 12} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 10, 'NO_FACE': 2} | {'ENROLLED': 11, 'NO_FACE': 1} | {'ENROLLED': 10, 'NO_FACE': 2} | yes |
| Finalized Events (rows) | 8 | 9 | 8 | yes |
| Events list (API) | 8 | 9 | 8 | yes |
| Effective participants (rows) | 17 | 21 | 17 | yes |
| Sightings (sum over People) | 17 | 21 | 17 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Laurel 2026-04-15→2026-04-15 f1.0; Maple None→None f0.0; Nutmeg None→None f0.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Laurel 2026-04-05→2026-04-15 f2.0; Maple 2026-04-05→2026-04-05 f1.0; Nutmeg 2026-04-05→2026-04-05 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Laurel 2026-04-15→2026-04-15 f1.0; Maple None→None f0.0; Nutmeg None→None f0.0 | yes |
| Event media refs (observation_media) | 15 | 19 | 15 | yes |
| Physical files (uploads/objects, faces, other) | (17, 19, 3) | (21, 23, 3) | (17, 19, 3) | yes |
| Face samples by state | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 22, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 19 | 23 | 19 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Laurel 0.620; maple→Birch 0.115; nutmeg→Nutmeg 0.642 | alder→Alder 0.676; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Laurel 0.651; maple→Maple 0.643; nutmeg→Nutmeg 0.729 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Laurel 0.620; maple→Birch 0.115; nutmeg→Nutmeg 0.642 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 2, 'RECOGNITION_DETAIL': 1} | {'PERSON': 2, 'RECOGNITION_DETAIL': 1} | {'PERSON': 2, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 3 | 3 | 3 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 2, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 15, 'MANUAL_ASSOCIATION': 2, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 2, 'NOTE_REFERENCE': 3} | yes |
| Graph connections (projection rows) | 13 | 19 | 13 | yes |
| Person Graph edges (Alder view) | 11 | 17 | 11 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm,Laurel,Maple,Nutmeg} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Laurel,Maple,Nutmeg} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Laurel,Maple,Nutmeg} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 12 | 18 | 12 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 8 | 14 | 8 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2; Laurel:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 2 | 2 | 2 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 3 | 2 | yes |
| Events pages (limit 2) | 4 | 5 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 19 | 18 | 19 | yes |
| Graph revision | 39 | 41 | 43 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'biometric_enrollment_history', 'embeddings', 'encounter_relation_decisions', 'graph_connections', 'graph_state', 'note_mentions', 'note_revision_mentions', 'note_revisions', 'notes', 'observation_face_assignments', 'observation_media', 'observation_participants', 'observations', 'operation_journal', 'operation_journal_status_history', 'person_change_history', 'person_operations', 'persons', 'photo_review_faces', 'photo_reviews', 'recognition_details', 'relationship_evidence']; API reads differing 93/313 (+7 ordering-only); files equal=True; eligibility equal=False; recognition differing=[]

### S5 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 6, 'ARCHIVED': 1, 'DELETED': 1, 'MERGED': 1} | {'ACTIVE': 7, 'ARCHIVED': 1, 'DELETED': 1, 'MERGED': 1} | {'ACTIVE': 6, 'ARCHIVED': 1, 'DELETED': 1, 'MERGED': 1} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 6} | {'ENROLLED': 6, 'NO_FACE': 1} | {'ENROLLED': 6} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 21 | 15 | yes |
| Sightings (sum over People) | 17 | 23 | 17 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Elm 2026-05-25→2026-05-25 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-28 f2.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.773; Elm 2026-05-25→2026-05-25 f1.0; Fir None→None f0.0; Hazel 2026-04-18→2026-04-28 f2.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-18→2026-04-28 f3.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Elm 2026-05-25→2026-05-25 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-28 f2.0 | yes |
| Event media refs (observation_media) | 13 | 19 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (20, 22, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 21, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 13 | 17 | 13 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Juniper 0.068; dogwood→Juniper 0.108; elm→Elm 0.654; fir→Elm 0.169; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Juniper 0.104; dogwood→Birch 0.170; elm→Elm 0.654; fir→Hazel 0.680; ginkgo→Juniper 0.129; hazel→Hazel 0.681; iris→Iris 0.719; juniper→Juniper 0.745; kauri→Birch 0.215; laurel→Birch 0.134; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Juniper 0.068; dogwood→Juniper 0.108; elm→Elm 0.654; fir→Elm 0.169; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 18, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 17 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 17 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Hazel,Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Iris,Juniper} | yes |
| World connections relationships | 9 | 16 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch,Cedar,Dogwood} {Hazel,Juniper} | {Alder,Birch} | yes |
| World explore relationships | 7 | 14 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Elm:1; Alder:1 | Birch:2; Elm:1; Alder:1 | Birch:2; Elm:1; Alder:1 | yes |
| Discoveries: most recent | Elm:1; Birch:1 | Elm:1; Birch:1 | Elm:1; Birch:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Juniper:2; Alder:2 | Cedar:3; Juniper:3; Birch:2; Alder:2; Hazel:2; Dogwood:2 | Cedar:2; Birch:2; Juniper:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 2 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 15 | 19 | 20 | **no** |
| Graph revision | 36 | 44 | 45 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'merge_affected_items', 'operation_journal', 'operation_journal_status_history', 'person_operations']; API reads differing 8/250 (+0 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S6 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 10} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 10} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 19 | 15 | yes |
| Sightings (sum over People) | 15 | 19 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm 2026-05-05→2026-05-05 f1.0; Ginkgo 2026-05-05→2026-05-05 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 17 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (18, 20, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'POOR_ACCEPTED': 1, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 20 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Elm 0.703; fir→Elm 0.238; ginkgo→Ginkgo 0.691; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.187; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 14, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 15 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 13 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Ginkgo} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 14 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 12 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:3; Alder:2; Elm:1; Ginkgo:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Birch:3; Alder:3; Cedar:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 3 | 2 | yes |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 34 | 36 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history', 'person_change_history']; API reads differing 2/254 (+6 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S7 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 11} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 10, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 17 | 15 | yes |
| Sightings (sum over People) | 15 | 17 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Kauri 2026-05-12→2026-05-12 f1.0; Maple 2026-05-12→2026-05-12 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 16 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (15, 17, 3) | (17, 19, 4) | (15, 17, 4) | **no** |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 17, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 18 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Kauri 0.654; laurel→Kauri 0.123; maple→Maple 0.629; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 11 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 8 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} {Kauri,Maple} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 10 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 8 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Kauri:1; Alder:1; Maple:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 3 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 35 | 36 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history', 'pending_additions']; API reads differing 1/254 (+6 ordering-only); files equal=False; eligibility equal=True; recognition differing=[]

### S8 — variant H2

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 10} | {'ACTIVE': 10} | **no** |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 2} | {'ENROLLED': 8, 'NO_FACE': 2} | **no** |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 18 | 15 | yes |
| Sightings (sum over People) | 15 | 18 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-01-15→2026-05-10 f4.0; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-01-15→2026-04-28 f2.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Nutmeg 2026-01-15→2026-01-15 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Nutmeg None→None f0.0 | **no** |
| Event media refs (observation_media) | 13 | 13 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (14, 16, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 16 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 11, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 13 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 12 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Hazel,Juniper Two,Nutmeg} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 12 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 10 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 3 | 2 | yes |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 16 | 17 | **no** |
| Graph revision | 30 | 33 | 34 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history', 'persons']; API reads differing 29/270 (+0 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S1 — variant H1

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 12} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 11, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 18 | 15 | yes |
| Sightings (sum over People) | 15 | 18 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Fir 2026-05-20→2026-05-20 f1.0; Ginkgo 2026-05-20→2026-05-20 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Kauri 2026-05-20→2026-05-20 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 15 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (16, 19, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 19 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Kauri 0.169; fir→Fir 0.603; ginkgo→Ginkgo 0.605; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Kauri 0.607; laurel→Kauri 0.113; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 2} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 3 | 2 | yes |
| Event Note selected mentions | 0 | 1 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 11, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 14 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 12 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Fir,Ginkgo,Kauri} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 13 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 10 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Fir:1; Alder:1; Ginkgo:1; Kauri:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 2 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | CRITICAL P11-JOURNAL-003 | **no** |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 37 | 38 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history']; API reads differing 0/254 (+12 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S1 — variant H1b

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 12} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 11, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 7 | yes |
| Events list (API) | 7 | 8 | 7 | yes |
| Effective participants (rows) | 15 | 18 | 15 | yes |
| Sightings (sum over People) | 15 | 18 | 15 | yes |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Fir 2026-05-20→2026-05-20 f1.0; Ginkgo 2026-05-20→2026-05-20 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Kauri 2026-05-20→2026-05-20 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 15 | 13 | yes |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (16, 19, 2) | (14, 16, 2) | yes |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 15, 'PROOF_ONLY': 1} | yes |
| Recognition-eligible samples | 16 | 19 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Kauri 0.169; fir→Fir 0.603; ginkgo→Ginkgo 0.605; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Kauri 0.607; laurel→Kauri 0.113; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 2} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 3 | 2 | yes |
| Event Note selected mentions | 0 | 1 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 11, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 14 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 12 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Fir,Ginkgo,Kauri} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 13 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 10 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Fir:1; Alder:1; Ginkgo:1; Kauri:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 2 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 37 | 38 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'graph_state', 'operation_journal', 'operation_journal_status_history']; API reads differing 0/254 (+12 ordering-only); files equal=True; eligibility equal=True; recognition differing=[]

### S1 — variant L

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 12} | {'ACTIVE': 9, 'DELETED': 3} | **no** |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 11, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 8 | **no** |
| Events list (API) | 7 | 8 | 8 | **no** |
| Effective participants (rows) | 15 | 18 | 18 | **no** |
| Sightings (sum over People) | 15 | 18 | 18 | **no** |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Fir 2026-05-20→2026-05-20 f1.0; Ginkgo 2026-05-20→2026-05-20 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Kauri 2026-05-20→2026-05-20 f1.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | yes |
| Event media refs (observation_media) | 13 | 15 | 15 | **no** |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (16, 19, 2) | (16, 19, 2) | **no** |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | **no** |
| Recognition-eligible samples | 16 | 19 | 16 | yes |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Kauri 0.169; fir→Fir 0.603; ginkgo→Ginkgo 0.605; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Kauri 0.607; laurel→Kauri 0.113; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | yes |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 2} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 3 | 2 | yes |
| Event Note selected mentions | 0 | 1 | 1 | **no** |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 11, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 14 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 12 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Fir,Ginkgo,Kauri} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 13 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 10 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Fir:1; Alder:1; Ginkgo:1; Kauri:1; Dogwood:1 | Birch:2; Fir:1; Alder:1; Ginkgo:1; Kauri:1; Dogwood:1 | **no** |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2 | yes |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 2 | 2 | **no** |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 37 | 41 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'embeddings', 'encounter_relation_decisions', 'experimental_deleted_events', 'graph_state', 'init_sessions', 'note_mentions', 'note_revision_mentions', 'note_revisions', 'notes', 'observation_face_assignments', 'observation_media', 'observation_participants', 'observations', 'operation_journal', 'operation_journal_status_history', 'persons', 'photo_review_faces', 'photo_review_media', 'photo_reviews', 'recognition_details', 'relationship_evidence']; API reads differing 78/307 (+8 ordering-only); files equal=False; eligibility equal=True; recognition differing=[]

### S2 — variant L

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 9} | {'ACTIVE': 9} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 8, 'NO_FACE': 1} | yes |
| Finalized Events (rows) | 7 | 8 | 8 | **no** |
| Events list (API) | 7 | 8 | 8 | **no** |
| Effective participants (rows) | 15 | 17 | 17 | **no** |
| Sightings (sum over People) | 15 | 17 | 17 | **no** |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-20 f2.812; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-20 f2.812; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | **no** |
| Event media refs (observation_media) | 13 | 16 | 16 | **no** |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (17, 19, 2) | (17, 19, 2) | **no** |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 18, 'PROOF_ONLY': 1} | **no** |
| Recognition-eligible samples | 16 | 19 | 19 | **no** |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.595; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.595; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | **no** |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 2} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 3 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 11 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 9 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 9 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch,Cedar} | {Alder,Birch} | yes |
| World explore relationships | 7 | 7 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:3; Alder:3; Birch:2 | Cedar:3; Alder:3; Birch:2 | **no** |
| Events search 'Delhi' | 2 | 3 | 3 | **no** |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 31 | 32 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'embeddings', 'encounter_relation_decisions', 'experimental_deleted_events', 'graph_state', 'init_sessions', 'note_mentions', 'note_revision_mentions', 'note_revisions', 'notes', 'observation_face_assignments', 'observation_media', 'observation_participants', 'observations', 'operation_journal', 'operation_journal_status_history', 'photo_review_faces', 'photo_review_media', 'photo_reviews', 'recognition_details', 'relationship_evidence']; API reads differing 82/259 (+4 ordering-only); files equal=False; eligibility equal=False; recognition differing=['linear.quality_only=True', 'linear.quality_only=False', 'hnsw.quality_only=True', 'hnsw.quality_only=False']

### S4 — variant L

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 12} | {'ACTIVE': 12} | {'ACTIVE': 12} | yes |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 10, 'NO_FACE': 2} | {'ENROLLED': 11, 'NO_FACE': 1} | {'ENROLLED': 11, 'NO_FACE': 1} | **no** |
| Finalized Events (rows) | 8 | 9 | 9 | **no** |
| Events list (API) | 8 | 9 | 9 | **no** |
| Effective participants (rows) | 17 | 21 | 21 | **no** |
| Sightings (sum over People) | 17 | 21 | 21 | **no** |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Laurel 2026-04-15→2026-04-15 f1.0; Maple None→None f0.0; Nutmeg None→None f0.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Laurel 2026-04-05→2026-04-15 f2.0; Maple 2026-04-05→2026-04-05 f1.0; Nutmeg 2026-04-05→2026-04-05 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0; Laurel 2026-04-05→2026-04-15 f2.0; Maple 2026-04-05→2026-04-05 f1.0; Nutmeg 2026-04-05→2026-04-05 f1.0 | **no** |
| Event media refs (observation_media) | 15 | 19 | 19 | **no** |
| Physical files (uploads/objects, faces, other) | (17, 19, 3) | (21, 23, 3) | (21, 23, 3) | **no** |
| Face samples by state | {'GOOD': 18, 'PROOF_ONLY': 1} | {'GOOD': 22, 'PROOF_ONLY': 1} | {'GOOD': 22, 'PROOF_ONLY': 1} | **no** |
| Recognition-eligible samples | 19 | 23 | 23 | **no** |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Laurel 0.620; maple→Birch 0.115; nutmeg→Nutmeg 0.642 | alder→Alder 0.676; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Laurel 0.651; maple→Maple 0.643; nutmeg→Nutmeg 0.729 | alder→Alder 0.676; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Laurel 0.651; maple→Maple 0.643; nutmeg→Nutmeg 0.729 | **no** |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 2, 'RECOGNITION_DETAIL': 1} | {'PERSON': 2, 'RECOGNITION_DETAIL': 1} | {'PERSON': 2, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 3 | 3 | 3 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 2, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 15, 'MANUAL_ASSOCIATION': 2, 'NOTE_REFERENCE': 3} | {'CO_OBSERVED': 9, 'MANUAL_ASSOCIATION': 2, 'NOTE_REFERENCE': 3} | yes |
| Graph connections (projection rows) | 13 | 19 | 13 | yes |
| Person Graph edges (Alder view) | 11 | 17 | 11 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm,Laurel,Maple,Nutmeg} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Laurel,Maple,Nutmeg} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Laurel,Maple,Nutmeg} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 12 | 18 | 12 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 8 | 14 | 8 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | Birch:2; Alder:1; Dogwood:1 | yes |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Cedar:2; Birch:2; Alder:2; Laurel:2 | Cedar:2; Birch:2; Alder:2; Laurel:2 | **no** |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 2 | 2 | 2 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 3 | 3 | **no** |
| Events pages (limit 2) | 4 | 5 | 5 | **no** |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 19 | 18 | 19 | yes |
| Graph revision | 39 | 41 | 42 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'biometric_enrollment_history', 'embeddings', 'encounter_relation_decisions', 'experimental_deleted_events', 'graph_connections', 'graph_state', 'init_sessions', 'note_mentions', 'note_revision_mentions', 'note_revisions', 'notes', 'observation_face_assignments', 'observation_media', 'observation_participants', 'observations', 'operation_journal', 'operation_journal_status_history', 'person_change_history', 'person_operations', 'persons', 'photo_review_faces', 'photo_review_media', 'photo_reviews', 'recognition_details', 'relationship_evidence']; API reads differing 135/318 (+8 ordering-only); files equal=False; eligibility equal=False; recognition differing=['linear.quality_only=True', 'linear.quality_only=False', 'hnsw.quality_only=True', 'hnsw.quality_only=False']

### S5 — variant L

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 6, 'ARCHIVED': 1, 'DELETED': 1, 'MERGED': 1} | {'ACTIVE': 7, 'ARCHIVED': 1, 'DELETED': 1, 'MERGED': 1} | {'ACTIVE': 6, 'ARCHIVED': 1, 'DELETED': 2, 'MERGED': 1} | **no** |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 6} | {'ENROLLED': 6, 'NO_FACE': 1} | {'ENROLLED': 6} | yes |
| Finalized Events (rows) | 7 | 8 | 8 | **no** |
| Events list (API) | 7 | 8 | 8 | **no** |
| Effective participants (rows) | 15 | 21 | 21 | **no** |
| Sightings (sum over People) | 17 | 23 | 23 | **no** |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Elm 2026-05-25→2026-05-25 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-28 f2.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.773; Elm 2026-05-25→2026-05-25 f1.0; Fir None→None f0.0; Hazel 2026-04-18→2026-04-28 f2.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-18→2026-04-28 f3.0 | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.773; Elm 2026-05-25→2026-05-25 f1.0; Hazel 2026-04-18→2026-04-28 f2.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-18→2026-04-28 f3.0 | **no** |
| Event media refs (observation_media) | 13 | 19 | 19 | **no** |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (20, 22, 2) | (20, 22, 2) | **no** |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 21, 'PROOF_ONLY': 1} | {'GOOD': 21, 'PROOF_ONLY': 1} | **no** |
| Recognition-eligible samples | 13 | 17 | 17 | **no** |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Juniper 0.068; dogwood→Juniper 0.108; elm→Elm 0.654; fir→Elm 0.169; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Juniper 0.104; dogwood→Birch 0.170; elm→Elm 0.654; fir→Hazel 0.680; ginkgo→Juniper 0.129; hazel→Hazel 0.681; iris→Iris 0.719; juniper→Juniper 0.745; kauri→Birch 0.215; laurel→Birch 0.134; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Juniper 0.104; dogwood→Birch 0.170; elm→Elm 0.654; fir→Hazel 0.680; ginkgo→Juniper 0.129; hazel→Hazel 0.681; iris→Iris 0.719; juniper→Juniper 0.745; kauri→Birch 0.215; laurel→Birch 0.134; maple→Birch 0.115; nutmeg→Alder 0.118 | **no** |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 18, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 17 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 17 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Hazel,Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Iris,Juniper} | yes |
| World connections relationships | 9 | 16 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch,Cedar,Dogwood} {Hazel,Juniper} | {Alder,Birch} | yes |
| World explore relationships | 7 | 14 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Elm:1; Alder:1 | Birch:2; Elm:1; Alder:1 | Birch:2; Elm:1; Alder:1 | yes |
| Discoveries: most recent | Elm:1; Birch:1 | Elm:1; Birch:1 | Elm:1; Birch:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Juniper:2; Alder:2 | Cedar:3; Juniper:3; Birch:2; Alder:2; Hazel:2; Dogwood:2 | Cedar:3; Juniper:3; Birch:2; Alder:2; Hazel:2; Dogwood:2 | **no** |
| Events search 'Delhi' | 2 | 2 | 2 | yes |
| Events search 'Goa' | 1 | 2 | 2 | **no** |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 15 | 19 | 20 | **no** |
| Graph revision | 36 | 44 | 46 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'embeddings', 'encounter_metadata_revisions', 'encounter_participant_revisions', 'encounter_relation_decisions', 'experimental_deleted_events', 'graph_state', 'identity_corrections', 'init_sessions', 'merge_affected_items', 'observation_face_assignments', 'observation_media', 'observation_participants', 'observations', 'operation_journal', 'operation_journal_status_history', 'person_operations', 'persons', 'photo_review_faces', 'photo_review_media', 'photo_reviews', 'recognition_details', 'relationship_evidence']; API reads differing 153/271 (+0 ordering-only); files equal=False; eligibility equal=False; recognition differing=['linear.quality_only=True', 'linear.quality_only=False', 'hnsw.quality_only=True', 'hnsw.quality_only=False']

### S6 — variant L

| Measure | Database A | Database B | Database B′ | Equivalent? |
|---|---|---|---|---|
| Persons by lifecycle | {'ACTIVE': 9} | {'ACTIVE': 10} | {'ACTIVE': 9, 'DELETED': 1} | **no** |
| ENROLLED / NO_FACE (active) | {'ENROLLED': 8, 'NO_FACE': 1} | {'ENROLLED': 10} | {'ENROLLED': 9} | **no** |
| Finalized Events (rows) | 7 | 8 | 8 | **no** |
| Events list (API) | 7 | 8 | 8 | **no** |
| Effective participants (rows) | 15 | 19 | 19 | **no** |
| Sightings (sum over People) | 15 | 19 | 19 | **no** |
| First/last seen, freq/30d | Alder 2026-03-02→2026-05-10 f1.293; Birch 2026-03-02→2026-05-25 f1.418; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm None→None f0.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm 2026-05-05→2026-05-05 f1.0; Ginkgo 2026-05-05→2026-05-05 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | Alder 2026-03-02→2026-05-10 f1.724; Birch 2026-03-02→2026-05-25 f1.773; Cedar 2026-03-20→2026-04-10 f2.0; Dogwood 2026-04-10→2026-05-25 f1.304; Elm 2026-05-05→2026-05-05 f1.0; Hazel 2026-04-28→2026-04-28 f1.0; Iris 2026-04-25→2026-04-25 f1.0; Juniper 2026-04-25→2026-04-25 f1.0; Juniper Two 2026-04-28→2026-04-28 f1.0 | **no** |
| Event media refs (observation_media) | 13 | 17 | 17 | **no** |
| Physical files (uploads/objects, faces, other) | (14, 16, 2) | (18, 20, 2) | (18, 20, 2) | **no** |
| Face samples by state | {'GOOD': 15, 'PROOF_ONLY': 1} | {'GOOD': 18, 'POOR_ACCEPTED': 1, 'PROOF_ONLY': 1} | {'GOOD': 18, 'POOR_ACCEPTED': 1, 'PROOF_ONLY': 1} | **no** |
| Recognition-eligible samples | 16 | 20 | 19 | **no** |
| Recognition top-1 (probe→name score) | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Cedar 0.130; fir→Alder 0.110; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.115; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Elm 0.703; fir→Elm 0.238; ginkgo→Ginkgo 0.691; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.187; nutmeg→Alder 0.118 | alder→Alder 0.664; birch→Birch 0.696; cedar→Cedar 0.423; dogwood→Dogwood 0.618; elm→Elm 0.703; fir→Elm 0.238; ginkgo→Juniper 0.129; hazel→Hazel 0.634; iris→Iris 0.719; juniper→Juniper Two 0.745; kauri→Birch 0.215; laurel→Birch 0.104; maple→Birch 0.187; nutmeg→Alder 0.118 | **no** |
| Linear == HNSW ranking (4 d.p.) | True | True | True | yes |
| Notes by scope (active) | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | {'PERSON': 1, 'RECOGNITION_DETAIL': 1} | yes |
| Active structured mentions | 2 | 2 | 2 | yes |
| Event Note selected mentions | 0 | 0 | 0 | yes |
| Active evidence by type | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 14, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | {'CO_OBSERVED': 8, 'MANUAL_ASSOCIATION': 1, 'NOTE_REFERENCE': 2} | yes |
| Graph connections (projection rows) | 10 | 15 | 10 | yes |
| Person Graph edges (Alder view) | 8 | 13 | 8 | yes |
| World connections clusters | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm,Ginkgo} {Hazel,Juniper Two} {Iris,Juniper} | {Alder,Birch,Cedar,Dogwood,Elm} {Hazel,Juniper Two} {Iris,Juniper} | yes |
| World connections relationships | 9 | 14 | 9 | yes |
| World explore clusters | {Alder,Birch} | {Alder,Birch} | {Alder,Birch} | yes |
| World explore relationships | 7 | 12 | 7 | yes |
| Discoveries: frequent (30d) | Birch:2; Alder:1; Dogwood:1 | Birch:3; Alder:2; Elm:1; Ginkgo:1; Dogwood:1 | Birch:3; Alder:2; Elm:1; Ginkgo:1; Dogwood:1 | **no** |
| Discoveries: most recent | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | Birch:1; Dogwood:1 | yes |
| Discoveries: multiple locations (90d) | Cedar:2; Birch:2; Alder:2 | Birch:3; Alder:3; Cedar:2 | Birch:3; Alder:3; Cedar:2 | **no** |
| Events search 'Delhi' | 2 | 3 | 3 | **no** |
| Events search 'Goa' | 1 | 1 | 1 | yes |
| Events search 'Mumbai' | 2 | 2 | 2 | yes |
| Events search 'Pune' | 2 | 2 | 2 | yes |
| Events pages (limit 2) | 4 | 4 | 4 | yes |
| Staged proposals naming erased/unknown | 0 | 0 | 0 | yes |
| Integrity (P11) | PASS | PASS | PASS | yes |
| Operation journal rows | 12 | 13 | 14 | **no** |
| Graph revision | 30 | 34 | 36 | **no** |

Differential totals A vs B′: DB tables differing ['app_users', 'auth_audit', 'embeddings', 'encounter_relation_decisions', 'experimental_deleted_events', 'graph_state', 'init_sessions', 'observation_face_assignments', 'observation_media', 'observation_participants', 'observations', 'operation_journal', 'operation_journal_status_history', 'person_change_history', 'persons', 'photo_review_faces', 'photo_review_media', 'photo_reviews', 'recognition_details', 'relationship_evidence']; API reads differing 116/275 (+4 ordering-only); files equal=False; eligibility equal=False; recognition differing=['linear.quality_only=True', 'linear.quality_only=False', 'hnsw.quality_only=True', 'hnsw.quality_only=False']

