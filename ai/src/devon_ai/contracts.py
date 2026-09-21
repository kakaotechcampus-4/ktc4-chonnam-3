"""Internal candidates and pure checks; never DB rows or public wire payloads.

See spec/ai/designs/2026-09-21-question-eval-contracts.md for the adopted subset.
Structural decoding alone does not establish semantic validity or BE acceptance.
"""

from dataclasses import dataclass, fields, is_dataclass
from types import UnionType
from typing import Literal, cast, get_args, get_origin, get_type_hints

PersonaId = Literal["tech_lead", "hr_manager", "domain_lead"]
FailureStage = Literal["parse", "schema", "semantic"]


class ContractError(ValueError):
    """A local failure with a safe field label, never the rejected raw value."""

    def __init__(self, stage: FailureStage, field: str) -> None:
        self.stage = stage
        super().__init__(f"{stage}: {field}")


class _Contract:
    def __post_init__(self) -> None:
        for name, annotation in get_type_hints(type(self)).items():
            _convert(annotation, getattr(self, name), name, wire=False)


def _convert(annotation: object, value: object, field: str, *, wire: bool) -> object:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Literal:
        if any(type(value) is type(option) and value == option for option in args):
            return value
    elif origin is UnionType:
        for option in args:
            try:
                return _convert(option, value, field, wire=wire)
            except ContractError:
                pass
    elif annotation is type(None) and value is None:
        return None
    elif annotation is str:
        if type(value) is str and value.strip():
            return value
    elif annotation is bool and type(value) is bool:
        return value
    elif origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        if type(value) is (list if wire else tuple):
            return tuple(_convert(args[0], item, field, wire=wire) for item in value)
    elif isinstance(annotation, type) and issubclass(annotation, _Contract):
        if not wire and type(value) is annotation:
            return value
        if wire and isinstance(value, dict) and is_dataclass(annotation):
            if set(value) == {item.name for item in fields(annotation)}:
                hints = get_type_hints(annotation)
                return annotation(
                    **{
                        name: _convert(kind, value[name], name, wire=True)
                        for name, kind in hints.items()
                    }
                )
    raise ContractError("schema", field)


def decode[T: _Contract](contract_type: type[T], payload: object) -> T:
    """Decode an already parsed object strictly; return an untrusted candidate."""
    return cast(T, _convert(contract_type, payload, contract_type.__name__, wire=True))


def _unique(values: tuple[str, ...], field: str) -> None:
    if len(set(values)) != len(values):
        raise ContractError("semantic", field)


@dataclass(frozen=True)
class Persona(_Contract):
    persona: PersonaId
    question_responsibilities: tuple[str, ...]
    avoided_assumptions: tuple[str, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.question_responsibilities or not self.avoided_assumptions:
            raise ContractError("schema", "persona configuration")


def validate_personas(personas: tuple[Persona, ...]) -> tuple[Persona, ...]:
    """Require the full FIX set; BE owns wording and its policy review."""
    _convert(tuple[Persona, ...], personas, "personas", wire=False)
    names = tuple(item.persona for item in personas)
    _unique(names, "personas")
    if set(names) != {"tech_lead", "hr_manager", "domain_lead"}:
        raise ContractError("semantic", "personas")
    return personas


@dataclass(frozen=True)
class RequiredPoint(_Contract):
    key: str
    description: str


@dataclass(frozen=True)
class QuestionContract(_Contract):
    purpose: str
    required_points: tuple[RequiredPoint, ...]
    assumptions: tuple[str, ...]
    basis_refs: tuple[str, ...]
    evaluation_scope: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.required_points:
            raise ContractError("schema", "required_points")
        _unique(tuple(point.key for point in self.required_points), "required_points")
        _unique(self.basis_refs, "basis_refs")
