import logging

log = logging.getLogger(__name__)

# -------------------------------------------------
# ETAP 3 – ZAPIS DO FALOWNIKA
# STEROWANIE WYŁĄCZNIE:
# - SOC
# - Grid / Disabled
# BRAK OBSŁUGI MOCY
# -------------------------------------------------


def write_plan(plan: dict, hass_api):
    """
    Wejście:
      plan      – wynik ETAPU 2 (planner_core)
      hass_api  – self z AppDaemon
    """

    log.info("=== INVERTER WRITER START ===")

    _apply_program(1, plan.get("target_soc_night"), "Grid", hass_api)
    _apply_program(2, plan.get("target_soc_midday"), "Grid", hass_api)

    # Pozostałe programy – wyłączone
    for idx in range(3, 7):
        _apply_program(idx, None, "Disabled", hass_api)

    log.info("=== INVERTER WRITER END ===")


# -------------------------------------------------
# ZAPIS JEDNEGO PROGRAMU
# -------------------------------------------------

def _apply_program(idx: int, target_soc, source: str, hass_api):
    """
    idx        – numer programu 1–6
    target_soc – docelowy SOC (None = nie ustawiaj)
    source     – "Grid" lub "Disabled"
    """

    log.info(f"Program {idx}: SOC={target_soc}, source={source}")

    hass_api.call_service(
        "select/select_option",
        entity_id=f"select.inverter_program_{idx}_charging",
        option=source,
    )

    if target_soc is not None:
        hass_api.call_service(
            "number/set_value",
            entity_id=f"number.inverter_program_{idx}_soc",
            value=target_soc,
        )
