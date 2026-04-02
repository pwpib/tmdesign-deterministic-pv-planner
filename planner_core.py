import logging
from datetime import datetime, timedelta
from . import config

log = logging.getLogger(__name__)

PV_DAWN_OFFSET_MIN = config.PV_DAWN_OFFSET_MIN
PV_DUSK_OFFSET_MIN = config.PV_DUSK_OFFSET_MIN

# Współczynniki podziału energii PV (z config.py)
PV_BEFORE_13_RATIO = config.PV_BEFORE_13_RATIO
PV_AFTER_13_RATIO = config.PV_AFTER_13_RATIO

# ==========================================================
# SYMULACJA OBCIĄŻENIEM POMPY CIEPŁA
# ==========================================================

def _calculate_hp_power(snapshot: dict) -> float:
    """
    Oblicza moc pompy ciepła na podstawie:
    - temperatury średniej jutro (snapshot)
    - modelu zużycia (snapshot/config)
    - tabeli mocy (snapshot/config)
    """

    temp = float(snapshot["temp_avg_tomorrow"])
    model = snapshot.get("heat_pump_model") or config.HEAT_PUMP_CONSUMPTION_MODEL

    hp_plus_15 = float(snapshot.get("heat_pump_power_at_plus_15", config.HEAT_PUMP_POWER_AT_PLUS_15))
    hp_plus_10 = float(snapshot.get("heat_pump_power_at_plus_10", config.HEAT_PUMP_POWER_AT_PLUS_10))
    hp_plus_5 = float(snapshot.get("heat_pump_power_at_plus_5", config.HEAT_PUMP_POWER_AT_PLUS_5))
    hp_0 = float(snapshot.get("heat_pump_power_at_0", config.HEAT_PUMP_POWER_AT_0))
    hp_minus_5 = float(snapshot.get("heat_pump_power_at_minus_5", config.HEAT_PUMP_POWER_AT_MINUS_5))
    hp_minus_10 = float(snapshot.get("heat_pump_power_at_minus_10", config.HEAT_PUMP_POWER_AT_MINUS_10))

    # --- wybór mocy bazowej zależnej od temperatury ---
    if temp >= 15:
        base_power = hp_plus_15
    elif temp >= 10:
        base_power = hp_plus_10
    elif temp >= 5:
        base_power = hp_plus_5
    elif temp >= 0:
        base_power = hp_0
    elif temp >= -5:
        base_power = hp_minus_5
    else:
        base_power = hp_minus_10

    # --- modyfikator modelu ---
    if model == "Eco":
        return base_power * 0.85
    elif model == "Premium":
        return base_power * 1.15
    else:
        return base_power

# ==========================================================
# GŁÓWNA FUNKCJA
# ==========================================================

def run(snapshot: dict) -> dict:

    log.info("=== PLANNER CORE V3 START ===")

    log.info(f"DEBUG dawn raw: {snapshot['sun_next_dawn']}")
    log.info(f"DEBUG dusk raw: {snapshot['sun_next_dusk']}")
    log.info(f"DEBUG plan_date: {snapshot['plan_date']}")

    _validate_snapshot(snapshot)

    capacity = float(snapshot["battery_capacity_kwh"])
    soc_max = float(snapshot["battery_soc_max"])

    # ---- sezon ----
    heating_active = snapshot.get("heating_season_active")
    summer_active = snapshot.get("summer_season_active")

    if heating_active is True:
        soc_min = float(snapshot["battery_soc_min_winter"])
        season = "winter"
    elif summer_active is True:
        soc_min = float(snapshot["battery_soc_min_summer"])
        season = "summer"
    elif snapshot["temp_avg_tomorrow"] <= snapshot["season_temperature_threshold"]:
        soc_min = float(snapshot["battery_soc_min_winter"])
        season = "winter"
    else:
        soc_min = float(snapshot["battery_soc_min_summer"])
        season = "summer"

    soc_min_kwh = capacity * soc_min / 100.0
    soc_max_kwh = capacity * soc_max / 100.0

    SOC_now = float(snapshot["battery_soc_now"])
    E = SOC_now / 100.0 * capacity
    log.info(f"DEBUG SOC_now: {SOC_now}%")
    log.info(f"DEBUG capacity: {capacity} kWh")

    PV_total = float(snapshot["pv_forecast_tomorrow"])
    pv_before_13_ratio = float(snapshot.get("energy_share_before_13", config.PV_BEFORE_13_RATIO))
    pv_after_13_ratio = float(snapshot.get("energy_share_after_13", config.PV_AFTER_13_RATIO))

    hp_power = _calculate_hp_power(snapshot)

    log.info(f"Start energy: {E:.2f} kWh")
    log.info(f"HP power: {hp_power:.2f} kW")
    log.info(f"PV forecast: {PV_total:.2f} kWh")

# ==========================================================
# SEKWENCYJNA SYMULACJA DNIA (PRZYCZYNOWA)
# ==========================================================

    SOC_06 = None
    SOC_13 = None

    timeline = []

    plan_date = datetime.fromisoformat(snapshot["plan_date"]).date()
    t0 = datetime.combine(plan_date, datetime.min.time())

    dawn = datetime.fromisoformat(snapshot["sun_next_dawn"]).replace(tzinfo=None)
    dusk = datetime.fromisoformat(snapshot["sun_next_dusk"]).replace(tzinfo=None)

    dawn = dawn.replace(year=plan_date.year, month=plan_date.month, day=plan_date.day)
    dusk = dusk.replace(year=plan_date.year, month=plan_date.month, day=plan_date.day)

    pv_start = dawn + timedelta(minutes=config.PV_DAWN_OFFSET_MIN)
    pv_end = dusk - timedelta(minutes=config.PV_DUSK_OFFSET_MIN)

    t06_limit = datetime.combine(plan_date, datetime.min.time()).replace(
        hour=config.PROGRAM_3_EARLIEST_HOUR, minute=config.PROGRAM_3_EARLIEST_MIN
    )
    if pv_start < t06_limit:
        pv_start = t06_limit

    t15_limit = datetime.combine(plan_date, datetime.min.time()).replace(
        hour=config.PROGRAM_6_EARLIEST_HOUR, minute=config.PROGRAM_6_EARLIEST_MIN
    )
    if pv_end < t15_limit:
        pv_end = t15_limit

    # Obliczenie czasu produkcji PV w godzinach (ze ułamkami minut)
    pv_hours_before_13 = 13.0 - pv_start.hour - pv_start.minute / 60.0
    pv_hours_after_13 = pv_end.hour + pv_end.minute / 60.0 - 13.0

    energy = E  # energia startowa (SOC_now)
    soc_min_kwh_local = soc_min_kwh

    for h in range(0, 24):

        current_time = t0 + timedelta(hours=h)

        # zużycie domu
        house_kw = config.get_house_load(h)

        # produkcja PV
        if current_time < pv_start or current_time >= pv_end:
            pv_kw = 0.0
        else:
            if current_time.hour < 13:
                pv_kw = (PV_total * pv_before_13_ratio) / max(1.0, pv_hours_before_13)
            else:
                pv_kw = (PV_total * pv_after_13_ratio) / max(1.0, pv_hours_after_13)

        load_kw = house_kw + hp_power
        energy = energy + pv_kw - load_kw

        if energy > soc_max_kwh:
            energy = soc_max_kwh

        if energy < soc_min_kwh_local:
            energy = soc_min_kwh_local

        timeline.append(energy)

    # ======================================================
    # OPTYMALIZACJA SOC_06 – minimalny poziom bez importu w drogiej taryfie
    # ======================================================

    # ======================================================
    # SOC_06 – okres 06:00 → 13:00
    # ======================================================

    def simulate_morning(start_percent):

        energy = capacity * start_percent / 100.0
        current_time = t0.replace(hour=6)

        while current_time.hour < 13:

            house_kw = config.get_house_load(current_time.hour)

            if current_time < pv_start or current_time >= pv_end:
                pv_kw = 0.0
            else:
                pv_kw = (PV_total * pv_before_13_ratio) / max(1.0, pv_hours_before_13)

            load_kw = house_kw + hp_power
            energy += pv_kw - load_kw

            if energy < soc_min_kwh:
                return False

            if energy > soc_max_kwh:
                energy = soc_max_kwh

            current_time += timedelta(hours=1)

        return True


    SOC_06 = None
    for candidate in range(int(soc_min), int(soc_max) + 1):
        if simulate_morning(candidate):
            SOC_06 = candidate
            break

    if SOC_06 is None:
        SOC_06 = int(soc_max)


    # ======================================================
    # SOC_13 – okres 15:00 → 22:00
    # ======================================================

    def simulate_evening(start_percent):

        energy = capacity * start_percent / 100.0
        current_time = t0.replace(hour=15)

        while current_time.hour < 22:

            house_kw = config.get_house_load(current_time.hour)
            load_kw = house_kw + hp_power

            energy -= load_kw

            if energy < soc_min_kwh:
                return False

            if energy > soc_max_kwh:
                energy = soc_max_kwh

            current_time += timedelta(hours=1)

        return True


    SOC_13 = None
    for candidate in range(int(soc_min), int(soc_max) + 1):
        if simulate_evening(candidate):
            SOC_13 = candidate
            break

    if SOC_13 is None:
        SOC_13 = int(soc_max)

    learning_bias = float(getattr(config, "LEARNING_SOC_TARGET_BIAS", 0.0))
    SOC_13 = int(round(SOC_13 + learning_bias))
    SOC_13 = max(int(soc_min), min(int(soc_max), SOC_13))

    log.info(f"SOC_06 target: {SOC_06}%")
    log.info(f"SOC_13 target: {SOC_13}%")
    log.info(f"Learning SOC bias: {learning_bias:+.2f} pp")

    programs = [
        {"program": 1, "soc": SOC_06},
        {"program": 2, "soc": int(soc_min)},
        {"program": 3, "soc": int(soc_min)},
        {"program": 4, "soc": SOC_13},
        {"program": 5, "soc": int(soc_min)},
        {"program": 6, "soc": int(soc_min)},
    ]

    plan = {
        "created_at": datetime.now().isoformat(),
        "plan_date": snapshot["plan_date"],
        "season": season,
        "pv_forecast_kwh": round(PV_total, 2),
        "heat_pump_energy_kwh": round(hp_power * 24, 2),
        "programs": programs,
        "pv_start_time": pv_start.strftime("%H:%M:%S"),
        "pv_end_time": pv_end.strftime("%H:%M:%S"),
        "target_soc_percent": SOC_13,
        "learning_soc_target_bias": learning_bias,
        "night_charge_kwh": 0.0,
        "midday_charge_kwh": 0.0

    }

    log.info("=== PLANNER CORE V3 END ===")
    return plan


# ==========================================================
# OKNA CZASOWE
# ==========================================================

def _build_time_windows(snapshot):

    plan_date = datetime.fromisoformat(snapshot["plan_date"]).date()

    dawn = datetime.fromisoformat(snapshot["sun_next_dawn"]).replace(tzinfo=None)
    dusk = datetime.fromisoformat(snapshot["sun_next_dusk"]).replace(tzinfo=None)

    dawn = dawn.replace(year=plan_date.year,
                        month=plan_date.month,
                        day=plan_date.day)

    dusk = dusk.replace(year=plan_date.year,
                        month=plan_date.month,
                        day=plan_date.day)

    # ----------------------------------------------------------
    # REALNY START PRODUKCJI PV
    # wschód + 2 godziny
    # ----------------------------------------------------------

    pv_start = dawn + timedelta(hours=2)

    t06 = datetime.combine(plan_date, datetime.min.time()).replace(hour=6, minute=1)

    # Program 3 nie może być wcześniejszy niż 06:01
    if pv_start < t06:
        pv_start = t06

    # ----------------------------------------------------------
    # REALNY KONIEC PRODUKCJI PV
    # zachód - 2 godziny
    # ----------------------------------------------------------

    pv_end = dusk - timedelta(hours=2)

    t15 = datetime.combine(plan_date, datetime.min.time()).replace(hour=15, minute=1)

    # Program 6 nie może być wcześniejszy niż 15:01
    if pv_end < t15:
        pv_end = t15

    # ----------------------------------------------------------

    t06_full = datetime.combine(plan_date, datetime.min.time()).replace(hour=6)
    t13 = datetime.combine(plan_date, datetime.min.time()).replace(hour=13)
    t22 = datetime.combine(plan_date, datetime.min.time()).replace(hour=22)

    def hours(a, b):
        if b <= a:
            return 0
        return (b - a).total_seconds() / 3600.0

    return [
        ("06", hours(t06_full, pv_start), 0.7, 0),
        ("13", hours(pv_start, t13), 0.7, PV_BEFORE_13_RATIO),
        ("13_15", hours(t13, t15), 0.7, 0),
        ("15", hours(t15, pv_end), 2.6, PV_AFTER_13_RATIO),
        ("22", hours(pv_end, t22), 1.6, 0),
    ]


# ==========================================================
# WALIDACJA
# ==========================================================

def _validate_snapshot(snapshot):

    required = [
        "plan_date",
        "temp_avg_tomorrow",
        "season_temperature_threshold",
        "sun_next_dawn",
        "sun_next_dusk",
        "battery_capacity_kwh",
        "battery_soc_min_winter",
        "battery_soc_min_summer",
        "battery_soc_max",
        #"heat_pump_power_at_plus_5",
        #"heat_pump_power_at_0",
        #"heat_pump_power_at_minus_5",
        #"heat_pump_power_at_minus_10",
        "pv_forecast_tomorrow",
    ]

    for k in required:
        if k not in snapshot:
            raise ValueError(f"Missing snapshot key: {k}")
