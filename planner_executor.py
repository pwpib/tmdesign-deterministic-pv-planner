from typing import Dict


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
        "target_soc_percent": plan.get("target_soc_percent"),
        "reason": None
    }

    night_kwh = plan.get("night_charge_kwh", 0)
    midday_kwh = plan.get("midday_charge_kwh", 0)

    if night_kwh > 0:
        decision["charge_night"] = True

    if midday_kwh > 0:
        decision["charge_midday"] = True

    if not decision["charge_night"] and not decision["charge_midday"]:
        decision["reason"] = "Brak ladowania plan zerowy lub ujemny"
    else:
        decision["reason"] = "Ladowanie zgodnie z planem"

    return decision

def map_decision_to_action(decision: dict) -> dict:
    """
    Mapuje decyzję logiczną na akcję systemową (bez wykonania).
    """
    action = {
        "grid_allowed": False,
        "target_soc_percent": decision.get("target_soc_percent"),
        "reason": decision.get("reason")
    }

    if decision["charge_night"] or decision["charge_midday"]:
        action["grid_allowed"] = True
    else:
        action["grid_allowed"] = False
        action["target_soc_percent"] = None
    return action
