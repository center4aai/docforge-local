"""Route-aware deterministic claim extraction and atomization."""

from __future__ import annotations

import re

from repo_autodocs.alignment_models import ClaimAtom, ClaimRecord, RouteName

_NEGATION = (" not ", " no ", " does not ", " do not ", " without ", " never ", " cannot ")
_RUNTIME_TOKENS = (
    "fast",
    "low-latency",
    "latency",
    "performant",
    "performance",
    "production-ready",
    "easy to use",
    "reliable ux",
    "real-time",
    "high quality",
    "under 50ms",
    "50ms",
    "responds in",
    "network behavior",
)


def extract_route_claims(
    *, route: RouteName, source_path: str, source_kind: str, text: str
) -> list[ClaimRecord]:
    claims: list[ClaimRecord] = []
    for idx, (section_hint, segment) in enumerate(_extract_segments(text)):
        claim_text = _clean(segment)
        if not claim_text:
            continue
        claim_id = f"{source_path}:{idx}"
        atoms, logic = atomize_claim(claim_id=claim_id, claim_text=claim_text)
        if not atoms:
            continue
        claim_type, verifiable, scope = _classify(route, claim_text)
        claims.append(
            ClaimRecord(
                claim_id=claim_id,
                route=route,
                source_path=source_path,
                source_kind=source_kind,
                source_section_hint=section_hint,
                original_text=claim_text,
                normalized_text=_norm(claim_text),
                language_hint="en",
                claim_type=claim_type,
                is_statically_verifiable=verifiable,
                logic=logic,
                atoms=tuple(atoms),
                is_verifiable_instruction=verifiable
                if route == "agent_instruction_alignment"
                else None,
                instruction_scope=scope if route == "agent_instruction_alignment" else None,
            )
        )
    return _dedupe(claims)


def atomize_claim(*, claim_id: str, claim_text: str) -> tuple[list[ClaimAtom], str]:
    parts, logic = _split_parts(claim_text)
    atoms: list[ClaimAtom] = []
    for idx, part in enumerate(parts):
        prior = atoms[-1] if atoms else None
        atom = _parse_atom(f"{claim_id}:a{idx}", part, prior_atom=prior)
        if atom:
            atoms.append(atom)
    if not atoms:
        return [], "single"
    return atoms, logic


def _extract_segments(text: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    section = "Document"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("#").strip() or section
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        items.append((section, line))
    return items


def _split_parts(text: str) -> tuple[list[str], str]:
    lowered = text.lower()
    logic = "single"
    if " or " in lowered:
        logic = "or"
    elif any(token in lowered for token in (" and ", " but ", ",")):
        logic = "and"

    parts = [text]
    for splitter in (r"\s+but\s+", r"\s+and\s+", r"\s*,\s*"):
        next_parts: list[str] = []
        for part in parts:
            next_parts.extend([p.strip(" .;") for p in re.split(splitter, part) if p.strip(" .;")])
        parts = next_parts
    return (parts or [text]), logic


def _parse_atom(atom_id: str, fragment: str, *, prior_atom: ClaimAtom | None) -> ClaimAtom | None:
    lowered = _norm(fragment)
    polarity = "negative" if any(token in f" {lowered} " for token in _NEGATION) else "positive"
    modality = "descriptive"
    if any(t in lowered for t in ("must", "required", "shall")):
        modality = "must"
    elif any(t in lowered for t in ("should", "recommended")):
        modality = "should"
    elif any(t in lowered for t in ("forbidden", "must not", "do not")):
        modality = "forbidden"

    command = re.search(r"docforge-local\s+([a-z][a-z0-9-]*)", lowered)
    if command:
        cmd = command.group(1)
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="cli",
            subject_value="docforge-local",
            predicate="cli_subcommand_exists",
            object_kind="cli_subcommand",
            object_value=cmd,
            polarity=polarity,
            modality=modality,
            qualifiers=(),
            anchor_terms=("docforge-local", cmd),
            alias_terms=(),
        )

    if prior_atom and prior_atom.predicate == "cli_subcommand_exists":
        cmd = re.search(r"\b([a-z][a-z0-9-]*-[a-z0-9-]+)\b", lowered)
        if cmd:
            return ClaimAtom(
                atom_id=atom_id,
                subject_kind=prior_atom.subject_kind,
                subject_value=prior_atom.subject_value,
                predicate=prior_atom.predicate,
                object_kind=prior_atom.object_kind,
                object_value=cmd.group(1),
                polarity=polarity,
                modality=modality,
                qualifiers=prior_atom.qualifiers,
                anchor_terms=("docforge-local", cmd.group(1)),
                alias_terms=(),
            )

    page = re.search(r"(?:generated/)?([a-z_]+)\.md", lowered)
    if page:
        name = page.group(1)
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="docs",
            subject_value="generated",
            predicate="generated_page_exists",
            object_kind="generated_page",
            object_value=name,
            polarity=polarity,
            modality=modality,
            anchor_terms=(name,),
            qualifiers=(),
            alias_terms=(),
        )

    if prior_atom and prior_atom.predicate == "generated_page_exists":
        page_name = re.search(r"\b([a-z_]+)\b", lowered)
        if page_name:
            return ClaimAtom(
                atom_id=atom_id,
                subject_kind="docs",
                subject_value="generated",
                predicate="generated_page_exists",
                object_kind="generated_page",
                object_value=page_name.group(1),
                polarity=polarity,
                modality=modality,
                qualifiers=(),
                anchor_terms=(page_name.group(1),),
                alias_terms=(),
            )

    if "generated_text_language" in lowered or (
        "supports" in lowered and any(v in lowered for v in (" en", " ru"))
    ):
        value = "ru" if " ru" in f" {lowered} " else "en"
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="config_field",
            subject_value="generated_text_language",
            predicate="config_enum_contains_value",
            object_kind="config_enum_value",
            object_value=value,
            polarity=polarity,
            modality=modality,
            anchor_terms=("generated_text_language", value),
            qualifiers=(),
            alias_terms=(),
        )

    if prior_atom and prior_atom.predicate == "config_enum_contains_value":
        if lowered in {"en", "ru"}:
            return ClaimAtom(
                atom_id=atom_id,
                subject_kind=prior_atom.subject_kind,
                subject_value=prior_atom.subject_value,
                predicate=prior_atom.predicate,
                object_kind=prior_atom.object_kind,
                object_value=lowered,
                polarity=polarity,
                modality=modality,
                anchor_terms=(prior_atom.subject_value, lowered),
                qualifiers=(),
                alias_terms=(),
            )

    if "maps to" in lowered and "first explicit reference path" in lowered:
        match = re.search(r"\b(reference_dir|methodology_dir)\b", lowered)
        if match:
            alias = match.group(1)
            return ClaimAtom(
                atom_id=atom_id,
                subject_kind="compatibility",
                subject_value=alias,
                predicate="compatibility_alias_maps_to_first_reference_path",
                object_kind="compatibility_target",
                object_value="first_explicit_reference_path",
                polarity=polarity,
                modality=modality,
                anchor_terms=(alias, "first_explicit_reference_path"),
                qualifiers=(),
                alias_terms=("reference_paths",),
            )

    if "maps to" in lowered:
        match = re.search(
            r"\b(reference_dir|methodology_dir)\b.*?maps\s+to\s+(?:the\s+)?\b([a-z_]+)\b", lowered
        )
        if match:
            return ClaimAtom(
                atom_id=atom_id,
                subject_kind="config_alias",
                subject_value=match.group(1),
                predicate="config_alias_maps_to_field",
                object_kind="config_field",
                object_value=match.group(2),
                polarity=polarity,
                modality=modality,
                anchor_terms=(match.group(1), match.group(2)),
                qualifiers=(),
                alias_terms=(),
            )

    if "readme" in lowered and "ignored" in lowered and "implementation" in lowered:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="policy",
            subject_value="readme",
            predicate="ignore_policy_excludes_target",
            object_kind="ignore_target",
            object_value="README.md",
            polarity=polarity,
            modality=modality,
            anchor_terms=("readme", "ignored"),
            qualifiers=(),
            alias_terms=(),
        )

    if (
        "agent" in lowered
        and "instruction" in lowered
        and "excluded" in lowered
        and "repo" in lowered
    ):
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="policy",
            subject_value="agent_instruction",
            predicate="ignore_policy_excludes_target",
            object_kind="ignore_target",
            object_value="**/AGENTS.md",
            polarity=polarity,
            modality=modality,
            anchor_terms=("agents.md", "excluded"),
            qualifiers=(),
            alias_terms=(),
        )

    if "readme" in lowered and "reference" in lowered:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="policy",
            subject_value="readme_reference_selection",
            predicate="ignore_policy_reference_selection_independent",
            object_kind="reference_selection",
            object_value="default_reference_targets_independent",
            polarity=polarity,
            modality=modality,
            anchor_terms=("readme", "reference", "selection"),
            qualifiers=(),
            alias_terms=(),
        )
    if "agent" in lowered and "instruction" in lowered and "reference" in lowered:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="policy",
            subject_value="agent_instruction_reference_selection",
            predicate="ignore_policy_reference_selection_independent",
            object_kind="reference_selection",
            object_value="default_reference_targets_independent",
            polarity=polarity,
            modality=modality,
            anchor_terms=("agent instruction", "reference", "selection"),
            qualifiers=(),
            alias_terms=(),
        )
    if "explicit reference" in lowered and "ignore" in lowered:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="policy",
            subject_value="explicit_reference_paths",
            predicate="ignore_policy_reference_selection_independent",
            object_kind="reference_selection",
            object_value="explicit_reference_paths_independent",
            polarity=polarity,
            modality=modality,
            anchor_terms=("explicit", "reference", "ignore"),
            qualifiers=(),
            alias_terms=(),
        )
    if (
        prior_atom
        and prior_atom.predicate == "ignore_policy_excludes_target"
        and "reference" in lowered
    ):
        relation = (
            "default_reference_targets_independent"
            if prior_atom.object_value in {"README.md", "**/AGENTS.md"}
            else "explicit_reference_paths_independent"
        )
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="policy",
            subject_value=prior_atom.subject_value,
            predicate="ignore_policy_reference_selection_independent",
            object_kind="reference_selection",
            object_value=relation,
            polarity=polarity,
            modality=modality,
            anchor_terms=("reference", "selection"),
            qualifiers=(),
            alias_terms=(),
        )

    alias = re.search(r"\b(reference_dir|methodology_dir|ground-methodology)\b", lowered)
    if alias and "maps to" not in lowered:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="compatibility",
            subject_value=alias.group(1),
            predicate="compatibility_alias_exists",
            object_kind="compatibility_alias",
            object_value=alias.group(1),
            polarity=polarity,
            modality=modality,
            anchor_terms=(alias.group(1),),
            qualifiers=(),
            alias_terms=("reference_paths",),
        )

    field_match = re.search(r"\b([a-z_]{4,})\b", lowered)
    if field_match and any(k in lowered for k in ("config", "field", "env", "setting")):
        key = field_match.group(1)
        predicate = "env_var_exists" if key.startswith("repo_autodocs_") else "config_field_exists"
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="config",
            subject_value=key,
            predicate=predicate,
            object_kind="env_var" if predicate == "env_var_exists" else "config_field",
            object_value=key,
            polarity=polarity,
            modality=modality,
            qualifiers=(),
            anchor_terms=(key,),
            alias_terms=(),
        )

    route_match = re.search(
        r"(reference_alignment|agent_instruction_alignment|readme_claim_alignment)", lowered
    )
    if "route" in lowered and route_match:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="routing",
            subject_value="routed_alignment",
            predicate="route_exists",
            object_kind="route_name",
            object_value=route_match.group(1),
            polarity=polarity,
            modality=modality,
            qualifiers=(),
            anchor_terms=(route_match.group(1),),
            alias_terms=(),
        )

    ep = re.search(r"([a-z_][a-z0-9_.]*:[a-z_][a-z0-9_]*)", lowered)
    if ep and "entrypoint" in lowered:
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="runtime",
            subject_value="entrypoint",
            predicate="entrypoint_exists",
            object_kind="entrypoint",
            object_value=ep.group(1),
            polarity=polarity,
            modality=modality,
            qualifiers=(),
            anchor_terms=(ep.group(1),),
            alias_terms=(),
        )

    if "typer" in lowered or "django" in lowered or "flask" in lowered:
        hint = "typer" if "typer" in lowered else "django" if "django" in lowered else "flask"
        return ClaimAtom(
            atom_id=atom_id,
            subject_kind="runtime",
            subject_value="framework",
            predicate="framework_hint_exists",
            object_kind="framework_hint",
            object_value=hint,
            polarity=polarity,
            modality=modality,
            qualifiers=(),
            anchor_terms=(hint,),
            alias_terms=(),
        )

    return ClaimAtom(
        atom_id=atom_id,
        subject_kind="text",
        subject_value=fragment,
        predicate="lexical_hint",
        object_kind=None,
        object_value=None,
        polarity=polarity,
        modality=modality,
        qualifiers=(),
        anchor_terms=tuple(tok for tok in _norm(fragment).split() if len(tok) >= 4)[:6],
        alias_terms=(),
    )


def _classify(route: RouteName, text: str) -> tuple[str, bool, str]:
    lowered = _norm(text)
    if route == "agent_instruction_alignment":
        if any(
            t in lowered
            for t in (
                "be concise",
                "be polite",
                "friendly tone",
                "tone",
                "high quality",
                "think step by step",
            )
        ):
            return "non_verifiable_guidance", False, "style"
        if any(t in lowered for t in ("before release", "run docforge-local", "workflow")):
            return "workflow_instruction", True, "workflow"
        if "config" in lowered:
            return "config_instruction", True, "config"
        if "ignore" in lowered:
            return "policy_instruction", True, "policy"
        if "output" in lowered or "generated" in lowered:
            return "output_instruction", True, "output"
        return "feature_instruction", True, "feature"

    if route == "readme_claim_alignment":
        if any(t in lowered for t in _RUNTIME_TOKENS):
            return "runtime_behavior", False, "unknown"
        if any(t in lowered for t in ("quality", "easy", "reliable", "experience")):
            return "quality_claim", False, "unknown"
        if "docforge-local" in lowered:
            return "cli_usage_static", True, "unknown"
        if "generated" in lowered or ".md" in lowered:
            return "generated_output_static", True, "unknown"
        if "config" in lowered or "env" in lowered:
            return "config_static", True, "unknown"
        return "capability_static", True, "unknown"

    if any(t in lowered for t in ("route", "alignment")):
        return "routing_requirement", True, "unknown"
    if any(t in lowered for t in ("compatibility", "alias", "preserve", "backward")):
        return "compatibility_requirement", True, "unknown"
    if any(t in lowered for t in ("ignore", "gitignore")):
        return "ignore_policy_requirement", True, "unknown"
    if any(t in lowered for t in ("config", "env", "setting")):
        return "config_requirement", True, "unknown"
    if any(t in lowered for t in ("generated", "output", "page")):
        return "output_requirement", True, "unknown"
    return "feature_requirement", True, "unknown"


def _dedupe(claims: list[ClaimRecord]) -> list[ClaimRecord]:
    seen: set[tuple[str, str]] = set()
    out: list[ClaimRecord] = []
    for claim in claims:
        key = (claim.source_path, claim.normalized_text)
        if key in seen:
            continue
        seen.add(key)
        out.append(claim)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"`([^`]+)`", r"\1", text)).strip(" -:;")


def _norm(text: str) -> str:
    lowered = text.casefold()
    lowered = re.sub(r"[^a-z0-9_\-./:\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()
