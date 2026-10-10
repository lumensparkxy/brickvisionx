"""Small strict model-facing contracts; no arbitrary executable commands or URLs."""
from typing import Literal
from pydantic import Field, model_validator
from ..core.models import StrictModel


class Panel(StrictModel):
    section: str = Field(pattern=r"^[a-z0-9-]+$")
    number: int | None
    label: str
    bbox: list[float] = Field(min_length=4, max_length=4)
    kind: Literal["main", "attachment", "substep"]

    @model_validator(mode="after")
    def bounds(self):
        x, y, right, bottom = self.bbox
        if not 0 <= x < right <= 1 or not 0 <= y < bottom <= 1 or (self.number is not None and self.number < 1):
            raise ValueError("Invalid instruction panel")
        return self


class PageIndex(StrictModel):
    panels: list[Panel]
    uncertainty: list[str]


class Construction(StrictModel):
    scene_json: str | None
    blockers: list[str]
    observations: list[str]


class Review(StrictModel):
    coverage_agrees: bool
    assembly_agrees: bool
    findings: list[str]


def strict_schema(model):
    schema = model.model_json_schema()
    # Model-facing strict outputs require every declared property, including nullable ones.
    def visit(node):
        if isinstance(node, dict):
            # Pydantic tuples use JSON Schema prefixItems; the provider accepts
            # homogeneous arrays with items instead. Keep exact length bounds.
            if node.get("type") == "array" and "prefixItems" in node:
                items = node.pop("prefixItems")
                if not items or any(item != items[0] for item in items):
                    raise ValueError("Model-facing tuples must have homogeneous item schemas")
                node["items"] = items[0]
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    return schema
