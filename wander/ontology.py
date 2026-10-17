"""Load, validate and change the ontology (ontology.yaml).

The ontology is the single source of truth for what the graph contains. Names are
validated strictly because they end up in Cypher (as labels, relationship types and
property keys), which can't be parameterised.

Changes are staged: anyone can *propose* one (it's validated and kept under `proposals:`),
but it only becomes part of the live ontology when a developer *applies* it after review.
Rejected proposals are kept under `rejected:` for the record.
"""

from __future__ import annotations

import copy
import datetime as dt
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
INITIAL_PATH = ROOT / "ontology.initial.yaml"

ENTITY_NAME = re.compile(r"^[A-Z][A-Za-z0-9]{0,39}$")
RELATIONSHIP_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")
PROPERTY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
RESERVED_PROPERTIES = {"id"}


class OntologyError(ValueError):
    """A proposed or loaded ontology isn't valid. The message is meant for a person."""


def ontology_path() -> Path:
    """Where the live ontology lives. Tests point WANDER_ONTOLOGY at a temporary copy."""
    return Path(os.environ.get("WANDER_ONTOLOGY", ROOT / "ontology.yaml"))


@dataclass
class Entity:
    name: str
    description: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Relationship:
    name: str
    from_: str
    to: str
    description: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class Ontology:
    entities: dict[str, Entity]
    relationships: dict[str, Relationship]
    changelog: list[dict]
    path: Path | None = None
    proposals: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)

    # ---- loading and saving -------------------------------------------------

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Ontology":
        path = Path(path) if path else ontology_path()
        raw = yaml.safe_load(path.read_text()) or {}
        onto = cls.from_dict(raw, path)
        onto.validate()
        return onto

    @classmethod
    def from_dict(cls, raw: dict, path: Path | None = None) -> "Ontology":
        entities = {
            name: Entity(name, spec.get("description", ""), dict(spec.get("properties") or {}))
            for name, spec in (raw.get("entities") or {}).items()
        }
        relationships = {
            name: Relationship(
                name,
                spec["from"],
                spec["to"],
                spec.get("description", ""),
                dict(spec.get("properties") or {}),
            )
            for name, spec in (raw.get("relationships") or {}).items()
        }
        changelog, proposals, rejected = ([_dates(dict(c)) for c in raw.get(key) or []]
                                          for key in ("changelog", "proposals", "rejected"))
        return cls(entities, relationships, changelog, path, proposals, rejected)

    def to_dict(self) -> dict:
        out: dict = {"entities": {}, "relationships": {}, "changelog": copy.deepcopy(self.changelog)}
        for e in self.entities.values():
            out["entities"][e.name] = {"description": e.description, "properties": dict(e.properties)}
        for r in self.relationships.values():
            spec = {"from": r.from_, "to": r.to, "description": r.description}
            if r.properties:
                spec["properties"] = dict(r.properties)
            out["relationships"][r.name] = spec
        if self.proposals:
            out["proposals"] = copy.deepcopy(self.proposals)
        if self.rejected:
            out["rejected"] = copy.deepcopy(self.rejected)
        return out

    def save(self) -> None:
        if self.path is None:
            raise OntologyError("This ontology has no file to save to.")
        header = (
            "# The ontology: which kinds of things exist in the business, and how they relate.\n"
            "# The graph only loads what is declared here. Proposed changes wait under `proposals:`\n"
            "# until a developer applies them (viewer: /review). `python -m wander.cli ontology reset`\n"
            "# restores ontology.initial.yaml.\n\n"
        )
        body = yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True, width=100)
        self.path.write_text(header + body)

    # ---- validation ---------------------------------------------------------

    def validate(self) -> None:
        for e in self.entities.values():
            _check_name(e.name, ENTITY_NAME, "entity", "PascalCase, e.g. Partner")
            for p in e.properties:
                _check_property(p)
        for r in self.relationships.values():
            _check_name(r.name, RELATIONSHIP_NAME, "relationship", "UPPER_SNAKE_CASE, e.g. REFERRED_BY")
            for end in (r.from_, r.to):
                if end not in self.entities:
                    raise OntologyError(
                        f"Relationship {r.name} refers to {end}, which isn't a declared entity."
                    )
            for p in r.properties:
                _check_property(p)
        clash = set(self.entities) & set(self.relationships)
        if clash:
            raise OntologyError(f"{', '.join(sorted(clash))} is both an entity and a relationship.")

    # ---- changes ------------------------------------------------------------

    def add_entity(self, name: str, description: str, properties: dict[str, str] | None,
                   proposed_by: str) -> str:
        _check_name(name, ENTITY_NAME, "entity", "PascalCase, e.g. Partner")
        if name in self.entities or name in self.relationships:
            raise OntologyError(f"{name} is already declared.")
        _require_description(description)
        props = dict(properties or {})
        for p in props:
            _check_property(p)
        if "name" not in props and "title" not in props:
            props = {"name": "Its name.", **props}
        self.entities[name] = Entity(name, description, props)
        return self._log(proposed_by, f"Added entity {name}: {description}")

    def add_property(self, entity: str, name: str, description: str, proposed_by: str) -> str:
        """Add a property to an entity, or to a relationship if `entity` names one."""
        _check_property(name)
        _require_description(description)
        target = self.entities.get(entity) or self.relationships.get(entity)
        if target is None:
            raise OntologyError(f"{entity} isn't a declared entity or relationship.")
        if name in target.properties:
            raise OntologyError(f"{entity} already has a property called {name}.")
        target.properties[name] = description
        return self._log(proposed_by, f"Added property {entity}.{name}: {description}")

    def add_relationship(self, name: str, from_: str, to: str, description: str,
                         properties: dict[str, str] | None, proposed_by: str) -> str:
        _check_name(name, RELATIONSHIP_NAME, "relationship", "UPPER_SNAKE_CASE, e.g. REFERRED_BY")
        if name in self.relationships or name in self.entities:
            raise OntologyError(f"{name} is already declared.")
        for end in (from_, to):
            if end not in self.entities:
                raise OntologyError(
                    f"{end} isn't a declared entity. Declare it first, then the relationship."
                )
        _require_description(description)
        props = dict(properties or {})
        for p in props:
            _check_property(p)
        self.relationships[name] = Relationship(name, from_, to, description, props)
        return self._log(proposed_by, f"Added relationship {from_} -[{name}]-> {to}: {description}")

    def apply(self, change: dict) -> str:
        """Apply one change straight to this ontology: {kind, name, description, ...}.

        The live ontology only changes through apply_proposals (after review); this is the
        step it uses, and what scenario checks use on an in-memory copy.
        """
        kind = change.get("kind")
        by = change.get("proposed_by", "")
        if kind == "entity":
            return self.add_entity(change.get("name"), change.get("description", ""),
                                   change.get("properties"), by)
        if kind == "property":
            return self.add_property(change.get("entity"), change.get("name"),
                                     change.get("description", ""), by)
        if kind == "relationship":
            return self.add_relationship(change.get("name"), change.get("from"), change.get("to"),
                                         change.get("description", ""), change.get("properties"), by)
        raise OntologyError("kind must be entity, property or relationship.")

    # ---- staged changes: propose, review, apply, reject -------------------------

    def propose(self, change: dict) -> dict:
        """Validate a change and stage it. Nothing becomes live until it's applied."""
        change = _clean(change)
        if not change.get("proposed_by"):
            raise OntologyError("Say who is proposing it, so the change log can credit them.")
        summary = self.with_pending().apply(change)  # valid on top of everything already proposed?
        summary = re.sub(r"^Added ", "Add ", summary)
        proposal = {"id": self._next_id(), **change, "proposed_at": dt.date.today().isoformat(),
                    "summary": summary}
        self.proposals.append(proposal)
        return proposal

    def with_pending(self, ids: set[str] | None = None) -> "Ontology":
        """A copy with the pending proposals applied in order (only `ids`, if given)."""
        trial = self.copy()
        for p in self.proposals:
            if ids is None or p["id"] in ids:
                try:
                    trial.apply(p)
                except OntologyError:
                    pass
        return trial

    def review(self) -> list[dict]:
        """Every pending proposal, checked as if all the earlier ones were applied."""
        trial, out = self.copy(), []
        for p in self.proposals:
            try:
                trial.apply(p)
                out.append({**p, "valid": True})
            except OntologyError as e:
                out.append({**p, "valid": False, "problem": str(e)})
        return out

    def apply_proposals(self, ids: list[str], reviewed_by: str) -> list[dict]:
        """Make the chosen proposals live, in the order they were proposed. All or nothing."""
        reviewed_by = (reviewed_by or "").strip()
        if not reviewed_by:
            raise OntologyError("Say who reviewed these changes, for the change log.")
        chosen_ids = set(ids)
        unknown = chosen_ids - {p["id"] for p in self.proposals}
        if unknown:
            raise OntologyError(f"No pending proposal {', '.join(sorted(unknown))}.")
        chosen = [p for p in self.proposals if p["id"] in chosen_ids]
        if not chosen:
            raise OntologyError("Choose at least one proposal to apply.")
        trial = self.copy()
        for p in chosen:
            try:
                trial.apply(p)
            except OntologyError as e:
                raise OntologyError(f"Can't apply {p['id']} ({p['name']}): {e} "
                                    "If it builds on another proposal, apply that one too.") from e
        for p in chosen:
            self.apply(p)
            self.changelog[-1].update({"proposal": p["id"], "proposed_at": p["proposed_at"],
                                       "reviewed_by": reviewed_by})
        self.proposals = [p for p in self.proposals if p["id"] not in chosen_ids]
        return chosen

    def reject(self, pid: str, reviewed_by: str, reason: str = "") -> dict:
        reviewed_by = (reviewed_by or "").strip()
        if not reviewed_by:
            raise OntologyError("Say who reviewed it, for the record.")
        match = [p for p in self.proposals if p["id"] == pid]
        if not match:
            raise OntologyError(f"No pending proposal {pid}.")
        record = {**match[0], "rejected_by": reviewed_by, "rejected_at": dt.date.today().isoformat(),
                  "reason": (reason or "").strip() or "No reason given."}
        self.proposals = [p for p in self.proposals if p["id"] != pid]
        self.rejected.append(record)
        return record

    def _next_id(self) -> str:
        used = [c.get("proposal") or c.get("id") for c in self.proposals + self.rejected + self.changelog]
        nums = [int(x[1:]) for x in used if isinstance(x, str) and re.fullmatch(r"p\d+", x)]
        return f"p{max(nums, default=0) + 1}"

    def copy(self) -> "Ontology":
        """An in-memory copy that can't be saved over the live file."""
        return Ontology.from_dict(self.to_dict(), None)

    def _log(self, by: str, change: str) -> str:
        by = (by or "").strip() or "unknown"
        self.changelog.append({"date": dt.date.today().isoformat(), "by": by, "change": change})
        return change

    # ---- reading --------------------------------------------------------------

    def label_property(self, entity: str) -> str | None:
        props = self.entities[entity].properties
        for candidate in ("name", "title"):
            if candidate in props:
                return candidate
        return None

    def describe(self) -> str:
        """The ontology in plain language, for a business reader (and for Claude)."""
        lines = ["Things the graph knows about:"]
        for e in self.entities.values():
            lines.append(f"\n{e.name} — {e.description}")
            for p, d in e.properties.items():
                lines.append(f"  • {p}: {d}")
        lines.append("\nHow they connect:")
        for r in self.relationships.values():
            lines.append(f"\n{r.from_} -[{r.name}]-> {r.to} — {r.description}")
            for p, d in r.properties.items():
                lines.append(f"  • {p}: {d}")
        if self.changelog:
            lines.append("\nChanges:")
            for c in self.changelog:
                lines.append(f"  {c.get('date')} — {c.get('by')}: {c.get('change')}")
        return "\n".join(lines)


CHANGE_FIELDS = {
    "entity": ("kind", "name", "description", "properties", "proposed_by"),
    "property": ("kind", "entity", "name", "description", "proposed_by"),
    "relationship": ("kind", "name", "from", "to", "description", "properties", "proposed_by"),
}


def _clean(change: dict) -> dict:
    """Only the fields a change of its kind uses, with text trimmed."""
    if not isinstance(change, dict) or change.get("kind") not in CHANGE_FIELDS:
        raise OntologyError("kind must be entity, property or relationship.")
    out = {}
    for key in CHANGE_FIELDS[change["kind"]]:
        value = change.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, "", {}):
            out[key] = value
    return out


def _dates(entry: dict) -> dict:
    for k, v in entry.items():
        if isinstance(v, dt.date):
            entry[k] = v.isoformat()
    return entry


def reset(path: Path | str | None = None) -> Ontology:
    """Restore ontology.initial.yaml over the live ontology (pending proposals go too)."""
    path = Path(path) if path else ontology_path()
    shutil.copyfile(INITIAL_PATH, path)
    return Ontology.load(path)


def _check_name(name: str, pattern: re.Pattern, kind: str, hint: str) -> None:
    if not isinstance(name, str) or not pattern.match(name):
        raise OntologyError(f"'{name}' isn't a valid {kind} name. Use {hint}.")


def _check_property(name: str) -> None:
    if not isinstance(name, str) or not PROPERTY_NAME.match(name):
        raise OntologyError(f"'{name}' isn't a valid property name. Use snake_case, e.g. renewal_date.")
    if name in RESERVED_PROPERTIES:
        raise OntologyError(f"'{name}' is reserved.")


def _require_description(description: str) -> None:
    if not (description or "").strip():
        raise OntologyError("Please describe it in a sentence, so others know what it means.")
