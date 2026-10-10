"""CO2e factors and weight estimation.

CO2e factors are kg CO2e per kg of food, rounded category averages derived from Poore & Nemecek
(2018), "Reducing food's environmental impacts through producers and consumers", Science 360,
as republished by Our World in Data ("Environmental impacts of food"). Approximate: e.g. dairy
blends milk (~3) with cheese (~20); meat blends beef (~60) with pork/poultry (~7).
"""
CO2E_PER_KG = {
    "produce_leafy": 0.5,
    "produce_hardy": 0.7,
    "dairy": 4.5,
    "meat": 15.0,
    "seafood": 6.0,
    "bakery": 1.4,
    "eggs": 4.7,
    "leftovers": 3.0,
    "pantry_dry": 1.5,
    "frozen": 2.5,
    "other": 2.0,
}

# Typical mass of one "piece" per category, kg (rough supermarket averages).
PIECE_KG = {
    "produce_leafy": 0.25, "produce_hardy": 0.2, "dairy": 0.5, "meat": 0.45, "seafood": 0.3,
    "bakery": 0.4, "eggs": 0.06, "leftovers": 0.4, "pantry_dry": 0.5, "frozen": 0.5, "other": 0.3,
}
_UNIT_KG = {
    "kg": 1.0, "g": 0.001, "lb": 0.4536, "lbs": 0.4536, "oz": 0.02835,
    "l": 1.0, "liter": 1.0, "litre": 1.0, "ml": 0.001, "gallon": 3.785, "cup": 0.24,
}


def co2e_per_kg(category: str) -> float:
    return CO2E_PER_KG.get(category, CO2E_PER_KG["other"])


def estimate_weight_kg(category: str, quantity, unit: str | None) -> float:
    q = float(quantity if quantity is not None else 1)
    u = (unit or "piece").strip().lower()
    if u in _UNIT_KG:
        return round(q * _UNIT_KG[u], 4)
    if u == "dozen":
        q *= 12
    return round(q * PIECE_KG.get(category, PIECE_KG["other"]), 4)


def co2e_kg(category: str, weight_kg) -> float:
    return round(float(weight_kg or 0) * co2e_per_kg(category), 4)
