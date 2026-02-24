import logging

log = logging.getLogger(__name__)

# --------------------------------------------------
# ETAP 3 – ZAPIS DO FALOWNIKA
# STEROWANIE WYŁĄCZNIE:
# - SOC
# BRAK OBSŁUGI GRID / DISABLED
# ---------------------------------------------------


def write_plan(plan: dict, hass_api):
    """
    Wejście:
      plan      – wynik ETAPU 2 (planner_core)
      hass_api  – self z AppDaemon
    """

    log.info("=== INVERTER WRITER START ===")

    programs = plan.get("programs", [])

    for program in programs:
        idx = program["program"]
        target_soc = program["soc"]

        _apply_program(idx, target_soc, hass_api)

    log.info("=== INVERTER WRITER END ===")


# -------------------------------------------------
# ZAPIS JEDNEGO PROGRAMU
# -------------------------------------------------

def _apply_program(idx: int, target_soc, hass_api):
    """
    idx        – numer programu 1–6
    target_soc – docelowy SOC
    """

    log.info(f"Program {idx}: SOC={target_soc}")

    hass_api.call_service(
        "number/set_value",
        entity_id=f"number.inverter_program_{idx}_soc",
        value=target_soc,
    )
