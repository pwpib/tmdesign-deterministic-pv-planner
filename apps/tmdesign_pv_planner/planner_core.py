import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

PV_DAWN_OFFSET_MIN = 45
PV_DUSK_OFFSET_MIN = 30
HOUSE_BASE_LOAD_KW = 1.0   # stałe zużycie domu


# ==========================================================
# GŁÓWNA FUNKCJA
# ==========================================================

def run(snapshot: dict) -> dict:

    log.info("=== PLANNER CORE START ===")

    _validate_snapshot(snapshot)

    # ===============================
    # PARAMETRY PODSTAWOWE
    # ===============================

    pv_forecast = snapshot["pv_forecast_tomorrow"]

    battery_capacity = snapshot["battery_capacity_kwh"]
    if battery_capacity > 100:
        battery_capacity /= 1000.0

    battery_now = snapshot["battery_energy_now_kwh"]
    if battery_now > 100:
        battery_now /= 1000.0

    soc_min = (
        snapshot["battery_soc_min_winter"]
        if snapshot["heating_season_active"]
        else snapshot["battery_soc_min_summer"]
    )

    soc_min_kwh = battery_capacity * soc_min / 100.0

    # ===============================
    # ZUŻYCIE
    # ===============================

    season = _detect_season(snapshot)

    hp_power = _calculate_heat_pump_power(snapshot)
    hp_energy = hp_power * 24

    HOUSE_BASE_LOAD_KW = 1.0
    house_energy = 24 * HOUSE_BASE_LOAD_KW

    total_load = hp_energy + house_energy

    # ===============================
    # OKNA PV (GODZINOWE)
    # ===============================

    pv_start, pv_end = _calculate_pv_window(snapshot)

    day_start = pv_start.replace(hour=6, minute=0, second=0)
    day_end = pv_start.replace(hour=22, minute=0, second=0)

    morning_hours = max(0.0, (pv_start - day_start).total_seconds() / 3600.0)
    evening_hours = max(0.0, (day_end - pv_end).total_seconds() / 3600.0)

    avg_load_kw = hp_power + HOUSE_BASE_LOAD_KW

    energy_morning = morning_hours * avg_load_kw
    energy_evening = evening_hours * avg_load_kw

    log.info(f"PV forecast: {pv_forecast:.2f} kWh")
    log.info(f"Total load: {total_load:.2f} kWh")
    log.info(f"Morning hours: {morning_hours:.2f}")
    log.info(f"Evening hours: {evening_hours:.2f}")

    # ===============================
    # TARGET SOC – MODEL FIZYCZNY
    # ===============================

    target_soc_rano_kwh = energy_morning + soc_min_kwh
    target_soc_15_kwh = energy_evening + soc_min_kwh

    target_soc_rano = int(round((target_soc_rano_kwh / battery_capacity) * 100))
    target_soc_15 = int(round((target_soc_15_kwh / battery_capacity) * 100))

    if target_soc_rano > 100:
        target_soc_rano = 100

    if target_soc_15 > 100:
        target_soc_15 = 100

    if target_soc_rano < soc_min:
        target_soc_rano = int(soc_min)

    if target_soc_15 < soc_min:
        target_soc_15 = int(soc_min)

    # ===============================
    # BILANS DNIA (NADPISANIE STRATEGICZNE)
    # ===============================

    net_balance = pv_forecast - total_load

    if net_balance < -0.2 * total_load:
        # DUŻY DEFICYT → pełne zabezpieczenie
        target_soc_rano = 100
        target_soc_15 = 100
        day_type = "DEFICIT"

    elif net_balance > 0.3 * battery_capacity:
        # DUŻY NADMIAR → maksymalne opróżnianie
        target_soc_rano = int(soc_min)
        target_soc_15 = int(soc_min)
        day_type = "SURPLUS"

    else:
        day_type = "BALANCED"

    log.info(f"Day type: {day_type}")
    log.info(f"Target rano: {target_soc_rano}%")
    log.info(f"Target 15: {target_soc_15}%")

    # ===============================
    # PLAN
    # ===============================

    plan = {
        "created_at": datetime.now().isoformat(),
        "plan_date": snapshot["plan_date"],
        "season": season,
        "pv_forecast_kwh": round(pv_forecast, 2),
        "heat_pump_energy_kwh": round(hp_energy, 2),
        "day_type": day_type,
        "programs": [
            {"program": 1, "soc": target_soc_rano, "charging": "Grid"},
            {"program": 2, "soc": target_soc_rano, "charging": "Disabled"},
            {"program": 3, "soc": 100, "charging": "Disabled"},
            {"program": 4, "soc": target_soc_15, "charging": "Grid"},
            {"program": 5, "soc": target_soc_15, "charging": "Disabled"},
            {"program": 6, "soc": int(soc_min), "charging": "Disabled"},
        ]
    }

    log.info(f"PLAN RESULT: {plan}")
    log.info("=== PLANNER CORE END ===")

    return plan


# ==========================================================
# OKNO PV
# ==========================================================

def _calculate_pv_window(snapshot: dict):

    plan_date = datetime.fromisoformat(snapshot["plan_date"]).date()

    dawn = datetime.fromisoformat(snapshot["sun_next_dawn"])
    dusk = datetime.fromisoformat(snapshot["sun_next_dusk"])

    if dawn.tzinfo:
        dawn = dawn.replace(tzinfo=None)
    if dusk.tzinfo:
        dusk = dusk.replace(tzinfo=None)

    # WYMUSZENIE DATY D+1
    dawn = dawn.replace(year=plan_date.year,
                        month=plan_date.month,
                        day=plan_date.day)

    dusk = dusk.replace(year=plan_date.year,
                        month=plan_date.month,
                        day=plan_date.day)

    pv_start = dawn + timedelta(minutes=PV_DAWN_OFFSET_MIN)
    pv_end = dusk - timedelta(minutes=PV_DUSK_OFFSET_MIN)

    # Minimalny realny start PV
    min_start = pv_start.replace(hour=8, minute=30, second=0)
    pv_start = max(pv_start, min_start)

    return pv_start, pv_end


# ==========================================================
# WALIDACJA
# ==========================================================

def _validate_snapshot(snapshot: dict):

    required = [
        "plan_date",
        "temp_avg_tomorrow",
        "season_temperature_threshold",
        "sun_next_dawn",
        "sun_next_dusk",
        "battery_energy_now_kwh",
        "battery_capacity_kwh",
        "battery_soc_min_winter",
        "battery_soc_min_summer",
        "battery_soc_max",
        "heat_pump_power_at_plus_5",
        "heat_pump_power_at_0",
        "heat_pump_power_at_minus_5",
        "heat_pump_power_at_minus_10",
        "heating_season_active",
    ]

    for k in required:
        if k not in snapshot:
            raise ValueError(f"Missing snapshot key: {k}")


# ==========================================================
# SEZON
# ==========================================================

def _detect_season(snapshot: dict):

    if snapshot["temp_avg_tomorrow"] <= snapshot["season_temperature_threshold"]:
        return "winter"
    return "summer"


# ==========================================================
# ŚREDNIA MOC POMPY
# ==========================================================

def _calculate_heat_pump_power(snapshot: dict):

    temp = snapshot["temp_avg_tomorrow"]

    p5 = snapshot["heat_pump_power_at_plus_5"]
    p0 = snapshot["heat_pump_power_at_0"]
    p_5 = snapshot["heat_pump_power_at_minus_5"]
    p_10 = snapshot["heat_pump_power_at_minus_10"]

    if temp >= 5:
        return p5
    elif temp >= 0:
        return _lerp(5, p5, 0, p0, temp)
    elif temp >= -5:
        return _lerp(0, p0, -5, p_5, temp)
    else:
        return _lerp(-5, p_5, -10, p_10, temp)


def _lerp(x1, y1, x2, y2, x):
    return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
