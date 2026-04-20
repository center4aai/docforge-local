# Output Contract

Generated documentation should follow this structure and remain consistent with the current CLI workflow.

## Required generated page set

1. `generated/overview.md`
2. `generated/architecture.md`
3. `generated/code_structure.md`
4. `generated/runtime_entrypoints.md`
5. `generated/reference_alignment.md`
6. `generated/agent_instruction_alignment.md`
7. `generated/readme_claim_alignment.md`
8. `generated/theory_alignment.md` (deprecated compatibility shim page)

## Rules

- Every generated section must be grounded in code facts, external reference materials, or both.
- The generator must distinguish:
  - observed implementation facts;
  - inferred explanations;
  - reference-material-driven intended design.
- If references and implementation diverge, routed alignment pages should contain explicit mismatch verdicts.

## Preferred documentation style

- concise, technical, explicit
- minimal fluff
- no fabricated certainty
- no hidden assumptions about runtime or deployment

## HTML publishing expectation

Generated Markdown must be compatible with MkDocs Material, remain readable in raw form inside the repository, and produce a locally browsable built site.
