from __future__ import annotations

from dataclasses import dataclass, field

from app.config import DOMAINS


@dataclass(frozen=True)
class RenderConfig:
    field_filter: str = "all"
    xw_angle: float = 35.0
    yz_angle: float = 20.0
    density: float = 0.5
    stroke_thickness: int = 2
    glow_strength: float = 0.45
    floor_shear: float = 0.18
    domains_enabled: dict[str, bool] = field(
        default_factory=lambda: {name: True for name in DOMAINS}
    )

    @classmethod
    def from_payload(cls, payload: dict) -> "RenderConfig":
        domain_flags = {name: bool(payload.get("domains_enabled", {}).get(name, True)) for name in DOMAINS}
        return cls(
            field_filter=str(payload.get("field_filter", "all")),
            xw_angle=float(payload.get("xw_angle", 35.0)),
            yz_angle=float(payload.get("yz_angle", 20.0)),
            density=max(0.1, min(1.0, float(payload.get("density", 0.5)))),
            stroke_thickness=max(1, min(8, int(payload.get("stroke_thickness", 2)))),
            glow_strength=max(0.0, min(1.0, float(payload.get("glow_strength", 0.45)))),
            floor_shear=max(-0.5, min(0.5, float(payload.get("floor_shear", 0.18)))),
            domains_enabled=domain_flags,
        )

    def active_domains(self) -> list[str]:
        if self.field_filter != "all":
            return [self.field_filter] if self.domains_enabled.get(self.field_filter, False) else []
        return [k for k, enabled in self.domains_enabled.items() if enabled]
