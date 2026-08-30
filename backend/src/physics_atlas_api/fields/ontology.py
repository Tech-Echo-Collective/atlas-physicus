"""Immutable Physics Atlas field vocabulary.

The ontology is intentionally independent from provider category systems.  Some
legacy public field identifiers resemble arXiv labels, but a matching string is
never itself evidence of field membership; provider evidence must pass through
the versioned mapping catalog.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

PHYSICS_FIELD_ONTOLOGY_VERSION = "physics-field-ontology-v1"
PHYSICS_DOMAIN_ID = "physics"

FieldNodeKind = Literal["branch", "field"]


@dataclass(frozen=True)
class FieldOntologyProvenance:
    source: str
    version: str
    status: Literal["reviewed-foundation"]
    note: str


PHYSICS_FIELD_ONTOLOGY_PROVENANCE = FieldOntologyProvenance(
    source="Physics Atlas field ontology",
    version=PHYSICS_FIELD_ONTOLOGY_VERSION,
    status="reviewed-foundation",
    note=(
        "A stable Atlas vocabulary for classification and future expansion; "
        "it does not imply live data coverage or metric activation."
    ),
)


@dataclass(frozen=True)
class FieldDefinition:
    id: str
    label: str
    description: str
    aliases: tuple[str, ...]
    parent_id: str | None
    node_kind: FieldNodeKind
    display_order: int
    ontology_version: str = PHYSICS_FIELD_ONTOLOGY_VERSION
    provenance: FieldOntologyProvenance = PHYSICS_FIELD_ONTOLOGY_PROVENANCE


@dataclass(frozen=True)
class PhysicsFieldOntology:
    version: str
    domain_id: str
    fields: tuple[FieldDefinition, ...]
    provenance: FieldOntologyProvenance
    _by_id: Mapping[str, FieldDefinition] = field(init=False, repr=False)
    _children: Mapping[str | None, tuple[FieldDefinition, ...]] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        by_id: dict[str, FieldDefinition] = {}
        display_orders: set[int] = set()
        for definition in self.fields:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", definition.id):
                raise ValueError(f"Invalid canonical field ID: {definition.id}")
            if definition.id in by_id:
                raise ValueError(f"Duplicate canonical field ID: {definition.id}")
            if definition.display_order in display_orders:
                raise ValueError(
                    f"Duplicate field display order: {definition.display_order}"
                )
            if definition.ontology_version != self.version:
                raise ValueError(
                    f"Field {definition.id} does not use ontology {self.version}"
                )
            if definition.provenance.version != self.version:
                raise ValueError(
                    f"Field {definition.id} provenance version is inconsistent"
                )
            normalized_aliases = [alias.casefold() for alias in definition.aliases]
            if any(not alias.strip() for alias in definition.aliases):
                raise ValueError(f"Field {definition.id} has an empty alias")
            if len(normalized_aliases) != len(set(normalized_aliases)):
                raise ValueError(f"Field {definition.id} has duplicate aliases")
            by_id[definition.id] = definition
            display_orders.add(definition.display_order)

        for definition in self.fields:
            if definition.parent_id is None:
                continue
            parent = by_id.get(definition.parent_id)
            if parent is None:
                raise ValueError(
                    f"Field {definition.id} has unknown parent {definition.parent_id}"
                )
            if parent.node_kind != "branch":
                raise ValueError(
                    f"Field {definition.id} has non-branch parent {parent.id}"
                )

        for definition in self.fields:
            visited = {definition.id}
            parent_id = definition.parent_id
            while parent_id is not None:
                if parent_id in visited:
                    raise ValueError(f"Ontology cycle reaches {parent_id}")
                visited.add(parent_id)
                parent_id = by_id[parent_id].parent_id

        children: dict[str | None, list[FieldDefinition]] = {}
        for definition in self.fields:
            children.setdefault(definition.parent_id, []).append(definition)
        frozen_children = {
            parent_id: tuple(sorted(items, key=lambda item: item.display_order))
            for parent_id, items in children.items()
        }
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        object.__setattr__(self, "_children", MappingProxyType(frozen_children))

    def get(self, field_id: str) -> FieldDefinition:
        return self._by_id[field_id]

    def contains(self, field_id: str) -> bool:
        return field_id in self._by_id

    def children_of(self, field_id: str | None) -> tuple[FieldDefinition, ...]:
        return self._children.get(field_id, ())

    def ancestors_of(self, field_id: str) -> tuple[FieldDefinition, ...]:
        ancestors: list[FieldDefinition] = []
        parent_id = self.get(field_id).parent_id
        while parent_id is not None:
            parent = self.get(parent_id)
            ancestors.append(parent)
            parent_id = parent.parent_id
        return tuple(ancestors)


PHYSICS_FIELD_DEFINITIONS_V1 = (
    FieldDefinition(
        id="hep",
        label="High Energy Physics",
        description=(
            "Theory, phenomenology, experiment, and lattice approaches in "
            "high-energy physics."
        ),
        aliases=("HEP", "High-Energy Physics", "Particle Physics"),
        parent_id=None,
        node_kind="branch",
        display_order=10,
    ),
    FieldDefinition(
        id="hep-th",
        label="High Energy Physics — Theory",
        description="Formal and theoretical aspects of high-energy physics.",
        aliases=("High Energy Theory", "HEP Theory", "Theoretical High-Energy Physics"),
        parent_id="hep",
        node_kind="field",
        display_order=20,
    ),
    FieldDefinition(
        id="hep-ph",
        label="High Energy Physics — Phenomenology",
        description=(
            "Phenomenological connections between high-energy theory and observation."
        ),
        aliases=("High Energy Phenomenology", "HEP Phenomenology"),
        parent_id="hep",
        node_kind="field",
        display_order=30,
    ),
    FieldDefinition(
        id="hep-ex",
        label="High Energy Physics — Experiment",
        description="Experimental methods and results in high-energy physics.",
        aliases=("High Energy Experiment", "Experimental High-Energy Physics"),
        parent_id="hep",
        node_kind="field",
        display_order=40,
    ),
    FieldDefinition(
        id="hep-lat",
        label="High Energy Physics — Lattice",
        description=(
            "Lattice and numerical field-theory approaches in high-energy physics."
        ),
        aliases=("Lattice Field Theory", "Lattice Gauge Theory", "Lattice HEP"),
        parent_id="hep",
        node_kind="field",
        display_order=50,
    ),
    FieldDefinition(
        id="gr-qc",
        label="Gravitation & Cosmology",
        description="Gravitation, relativity, cosmology, and quantum gravity.",
        aliases=(
            "General Relativity and Quantum Cosmology",
            "Gravity and Cosmology",
            "Gravitation and Cosmology",
        ),
        parent_id=None,
        node_kind="field",
        display_order=60,
    ),
    FieldDefinition(
        id="astro-ph",
        label="Astrophysics",
        description=(
            "Physical processes, systems, and observations in astronomy and "
            "astrophysics."
        ),
        aliases=("Astronomy and Astrophysics", "Astrophysics and Astronomy"),
        parent_id=None,
        node_kind="field",
        display_order=70,
    ),
    FieldDefinition(
        id="cond-mat",
        label="Condensed Matter",
        description="Theoretical and experimental physics of matter and materials.",
        aliases=("Condensed Matter Physics", "Condensed-Matter Physics"),
        parent_id=None,
        node_kind="field",
        display_order=80,
    ),
    FieldDefinition(
        id="amo",
        label="Atomic, Molecular & Optical Physics",
        description=(
            "Atomic, molecular, optical, and closely related light–matter physics."
        ),
        aliases=("AMO Physics", "Atomic Molecular and Optical Physics"),
        parent_id=None,
        node_kind="field",
        display_order=90,
    ),
    FieldDefinition(
        id="quant-ph",
        label="Quantum Science",
        description=(
            "Quantum information, foundations, technologies, and many-body "
            "quantum science."
        ),
        aliases=(
            "Quantum Information Science",
            "Quantum Physics",
            "Quantum Technologies",
        ),
        parent_id=None,
        node_kind="field",
        display_order=100,
    ),
    FieldDefinition(
        id="nuclear",
        label="Nuclear Physics",
        description=(
            "Structure, reactions, and fundamental properties of nuclei and "
            "nuclear matter."
        ),
        aliases=("Nuclear Science",),
        parent_id=None,
        node_kind="branch",
        display_order=110,
    ),
    FieldDefinition(
        id="nucl-th",
        label="Nuclear Physics — Theory",
        description="Theoretical nuclear physics.",
        aliases=("Nuclear Theory", "Theoretical Nuclear Physics"),
        parent_id="nuclear",
        node_kind="field",
        display_order=120,
    ),
    FieldDefinition(
        id="nucl-ex",
        label="Nuclear Physics — Experiment",
        description="Experimental nuclear physics.",
        aliases=("Nuclear Experiment", "Experimental Nuclear Physics"),
        parent_id="nuclear",
        node_kind="field",
        display_order=130,
    ),
    FieldDefinition(
        id="plasma",
        label="Plasma Physics",
        description="Fundamental and applied physics of plasmas.",
        aliases=("Plasma Science",),
        parent_id=None,
        node_kind="field",
        display_order=140,
    ),
    FieldDefinition(
        id="math-ph",
        label="Mathematical Physics",
        description=(
            "Mathematical structures, methods, and foundations used in physics."
        ),
        aliases=("Math Physics", "Mathematics and Mathematical Physics"),
        parent_id=None,
        node_kind="field",
        display_order=150,
    ),
    FieldDefinition(
        id="stat-nonlinear",
        label="Statistical & Nonlinear Physics",
        description=(
            "Statistical mechanics, complex systems, dynamics, and nonlinear phenomena."
        ),
        aliases=("Statistical Physics", "Nonlinear Physics", "Complex Systems Physics"),
        parent_id=None,
        node_kind="field",
        display_order=160,
    ),
    FieldDefinition(
        id="bio-soft-interdisciplinary",
        label="Biological / Soft / Interdisciplinary Physics",
        description=(
            "Physics-led study spanning biological, soft, and interdisciplinary "
            "systems."
        ),
        aliases=("Interdisciplinary Physics", "Biological and Soft-Matter Physics"),
        parent_id=None,
        node_kind="branch",
        display_order=170,
    ),
    FieldDefinition(
        id="biophysics",
        label="Biological Physics",
        description="Physical principles and methods applied to biological systems.",
        aliases=("Biophysics", "Physics of Biological Systems"),
        parent_id="bio-soft-interdisciplinary",
        node_kind="field",
        display_order=180,
    ),
    FieldDefinition(
        id="soft-matter",
        label="Soft Matter Physics",
        description=(
            "Physics of polymers, colloids, complex fluids, and other soft materials."
        ),
        aliases=("Soft Condensed Matter", "Soft-Matter Physics"),
        parent_id="bio-soft-interdisciplinary",
        node_kind="field",
        display_order=190,
    ),
)


PHYSICS_FIELD_ONTOLOGY_V1 = PhysicsFieldOntology(
    version=PHYSICS_FIELD_ONTOLOGY_VERSION,
    domain_id=PHYSICS_DOMAIN_ID,
    fields=PHYSICS_FIELD_DEFINITIONS_V1,
    provenance=PHYSICS_FIELD_ONTOLOGY_PROVENANCE,
)
