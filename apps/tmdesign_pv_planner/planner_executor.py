from typing import Optional, Dict


def decide_execution(plan: Dict) -> Dict:
    """
    Na podstawie planu na dziś zwraca decyzję wykonawczą.

    NIE steruje falownikiem.
    NIE używa Home Assistant.
    TYLKO logika.

    Zwraca słownik decyzji.
    """

    decision = {
        "charge_night": False,
        "charge_midday": False,
        "reason": None
    }

    night_kwh = plan.get("night_charge_kwh", 0)
    midday_kwh = plan.get("midday_charge_kwh", 0)

    if night_kwh > 0:
        decision["charge_night"] = True

    if midday_kwh > 0:
        decision["charge_midday"] = True

    if not decision["charge_night"] and not decision["charge_midday"]:
        decision["reason"] = "Brak ładowania – plan zerowy lub ujemny"
    else:
        decision["reason"] = "Ładowanie zgodnie z planem"

    return decision

def map_decision_to_action(decision: dict) -> dict:
    """
    Mapuje decyzję logiczną na akcję systemową (bez wykonania).
    """
    action = {
        "grid_mode": None,      # "Grid" albo "Disabled"
        "target_soc": None,     # docelowy SOC
        "reason": decision.get("reason")
    }

    if decision["charge_night"] or decision["charge_midday"]:
        action["grid_mode"] = "Grid"
        action["target_soc"] = "SOC_MAX"
    else:
        action["grid_mode"] = "Disabled"
        action["target_soc"] = "SOC_MIN"

    return action
