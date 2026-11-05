"""Map AEMO fuel text onto plain-English groups. No name guessing."""

from __future__ import annotations


def dispatch_class(dispatch_type: str | None) -> str:
    text = (dispatch_type or "").strip().lower()
    if "bidirectional" in text:
        return "bidirectional"
    if "generat" in text:
        return "generating"
    if "load" in text:
        return "load"
    if not text:
        return "unclassified"
    return "other"


def fuel_group(primary: str | None, technology: str | None, descriptor: str | None) -> str:
    primary_l = (primary or "").strip().lower()
    technology_l = (technology or "").strip().lower()
    descriptor_l = (descriptor or "").strip().lower()
    blob = " ".join(part for part in (primary_l, descriptor_l, technology_l) if part)
    if not blob:
        return "unclassified"
    if "battery" in blob or technology_l == "storage" or primary_l == "battery storage":
        return "storage"
    renewable_tokens = (
        "solar",
        "wind",
        "hydro",
        "bagasse",
        "landfill",
        "biogas",
        "biomass",
    )
    if any(token in blob for token in renewable_tokens) or technology_l == "renewable":
        return "renewable"
    fossil_tokens = (
        "coal",
        "gas",
        "diesel",
        "kerosene",
        "distillate",
        "fuel oil",
        "methane",
    )
    if any(token in blob for token in fossil_tokens) or technology_l == "fossil":
        return "fossil"
    return "other"


def fuel_chart(primary: str | None, group: str, descriptor: str | None = None) -> str:
    text = " ".join(
        part.strip().lower() for part in (primary or "", descriptor or "") if part and part.strip()
    )
    if group == "storage" or "battery" in text:
        return "Storage"
    if "wind" in text:
        return "Wind"
    if "solar" in text:
        return "Solar"
    if "hydro" in text:
        return "Hydro"
    if "coal seam" in text or "waste coal mine" in text:
        return "Gas"
    if "brown coal" in text:
        return "Brown coal"
    if "coal" in text:
        return "Coal"
    if any(token in text for token in ("gas", "methane")):
        return "Gas"
    if group == "renewable":
        return "Other renewable"
    if group == "fossil":
        return "Other fossil"
    if group == "unclassified":
        return "Unclassified"
    return "Other"
