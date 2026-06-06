from dataclasses import dataclass
from typing import Any


@dataclass
class Layer:
    name: str
    material: str
    thickness_nm: float | str
    active: bool = False
    coherent: bool = True
    n_source: str = "database"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Layer":
        return cls(
            name=str(data.get("name") or data.get("material") or "Layer"),
            material=str(data.get("material") or "air"),
            thickness_nm=data.get("thickness_nm", data.get("d", 0)),
            active=bool(data.get("active", False)),
            coherent=bool(data.get("coherent", True)),
            n_source=str(data.get("n_source", "database")),
        )

    def thickness_value(self) -> float:
        value = self.thickness_nm
        if isinstance(value, str) and value.lower() in {"inf", "infinity", "∞"}:
            return float("inf")
        return float(value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "material": self.material,
            "thickness_nm": self.thickness_nm,
            "active": self.active,
            "coherent": self.coherent,
            "n_source": self.n_source,
        }

