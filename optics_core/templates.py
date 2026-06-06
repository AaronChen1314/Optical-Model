from __future__ import annotations

from .models import Layer


def all_perovskite_planar_reference_template() -> list[Layer]:
    return [
        Layer("Air", "air", "inf"),
        Layer("Glass texture/equivalent", "glass", 1000),
        Layer("ITO", "ito", 100),
        Layer("NiO", "nio", 7),
        Layer("WBG active layer", "wbg_perovskite", 410, active=True),
        Layer("C60", "c60", 20),
        Layer("SnO2", "sno2", 20),
        Layer("ITO interconnect", "ito", 10),
        Layer("PEDOT:PSS", "pedot", 18),
        Layer("NBG active layer", "nbg_perovskite", 800, active=True),
        Layer("C60", "c60", 20),
        Layer("BCP", "bcp", 4),
        Layer("Ag back electrode", "ag", 150),
        Layer("Air rear", "air", "inf"),
    ]


def all_perovskite_legacy_tmm_template() -> list[Layer]:
    return [
        Layer("Air", "air", "inf"),
        Layer("ITO", "ito", 150),
        Layer("NiO", "nio", 7),
        Layer("WBG active layer", "wbg_perovskite", 400, active=True),
        Layer("C60", "c60", 20),
        Layer("SnO2", "sno2", 20),
        Layer("Au recombination", "au", 1),
        Layer("PEDOT:PSS", "pedot", 18),
        Layer("NBG active layer", "nbg_perovskite", 1150, active=True),
        Layer("C60", "c60", 20),
        Layer("BCP", "bcp", 4),
        Layer("Ag back electrode", "ag", 150),
        Layer("Glass substrate", "glass", "inf"),
    ]


def perovskite_silicon_template() -> list[Layer]:
    return [
        Layer("Air", "air", "inf"),
        Layer("MgF2 ARC", "mgf2", 100),
        Layer("IZO front", "izo", 20),
        Layer("BCP", "bcp", 4),
        Layer("C60", "c60", 5),
        Layer("Perovskite top cell", "perovskite_164", 410, active=True),
        Layer("IZO recombination", "izo", 5),
        Layer("a-Si n", "si_amorphous_n", 2),
        Layer("a-Si i front", "si_amorphous_i", 1),
        Layer("c-Si bottom cell", "si_crystalline", 200000, active=True),
        Layer("a-Si i rear", "si_amorphous_i", 5),
        Layer("a-Si p", "si_amorphous_p", 10),
        Layer("ITO rear", "ito", 50),
        Layer("Ag rear", "ag", 100),
        Layer("Air rear", "air", "inf"),
    ]


TEMPLATES = {
    "all_perovskite": all_perovskite_planar_reference_template,
    "all_perovskite_planar_reference": all_perovskite_planar_reference_template,
    "perovskite_silicon": perovskite_silicon_template,
}


def get_template(template_id: str) -> list[Layer]:
    if template_id not in TEMPLATES:
        raise KeyError(f"Unknown template: {template_id}")
    return TEMPLATES[template_id]()


def list_templates() -> list[dict]:
    return [
        {
            "id": "all_perovskite_planar_reference",
            "name": "All-perovskite tandem",
            "layers": [layer.to_dict() for layer in all_perovskite_planar_reference_template()],
        },
        {
            "id": "perovskite_silicon",
            "name": "Perovskite-silicon tandem",
            "layers": [layer.to_dict() for layer in perovskite_silicon_template()],
        },
    ]
