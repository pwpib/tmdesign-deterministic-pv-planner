"""
PV Planner Configuration
Parametry globalne systemu optymalizacji baterii
"""

# ==========================================================
# WSPÓŁCZYNNIKI PODZIAŁU ENERGII PV
# ==========================================================
# Określa, jaki procent prognozowanej energii PV pada
# przed 13:00 (rano) i po 13:00 (popołudnie)

PV_BEFORE_13_RATIO = 0.60  # 60% energii PV w przedziale 0–13h
PV_AFTER_13_RATIO = 0.40   # 40% energii PV w przedziale 13–24h


# ==========================================================
# OFFSETY CZASOWE SŁOŃCA
# ==========================================================
# Marginesy bezpieczeństwa dla czasów wschodu/zachodu słońca

PV_DAWN_OFFSET_MIN = 45    # Start produkcji PV: wschód + 45 min
PV_DUSK_OFFSET_MIN = 30    # Koniec produkcji PV: zachód - 30 min


# ==========================================================
# OGRANICZENIA CZASOWE PROGRAMÓW
# ==========================================================
# Program 3 nie może się uruchomić wcześniej niż 06:05
# Program 6 nie może się uruchomić wcześniej niż 15:05

PROGRAM_3_EARLIEST_HOUR = 6
PROGRAM_3_EARLIEST_MIN = 5

PROGRAM_6_EARLIEST_HOUR = 15
PROGRAM_6_EARLIEST_MIN = 5


# ==========================================================
# ZUŻYCIE DOMU (W TRAKCIE DOBY)
# ==========================================================
# Profil dobowy zapotrzebowania energii w kW

HOUSE_LOAD_PROFILE = {
    # Godziny 00–06: 0.4 kW (tryb nocny)
    "night": 0.4,
    # Godziny 06–15: 0.6 kW (poranek/dzień)
    "morning_day": 0.6,
    # Godziny 15–20: 1.6 kW (wieczór)
    "evening": 1.6,
    # Godziny 20–24: 1.0 kW (noc)
    "night_late": 1.0
}


# ==========================================================
# TARYFY PRĄDOWE
# ==========================================================
# Okresy taniej taryfy (domyślnie: noc + midday)

CHEAP_TARIFF_WINDOWS = [
    (22, 6),      # 22:00–06:00 (noc)
    (13, 15),     # 13:00–15:00 (midday)
]


# ==========================================================
# MOC POMPY CIEPŁA
# ==========================================================
# Moc poboru pompy ciepła w zależności od temperatury

HEAT_PUMP_POWER_AT_PLUS_15 = 1.0   # kW @ +15°C
HEAT_PUMP_POWER_AT_PLUS_10 = 1.0   # kW @ +10°C
HEAT_PUMP_POWER_AT_PLUS_5 = 1.0    # kW @ +5°C
HEAT_PUMP_POWER_AT_0 = 1.0         # kW @ 0°C
HEAT_PUMP_POWER_AT_MINUS_5 = 1.0   # kW @ -5°C
HEAT_PUMP_POWER_AT_MINUS_10 = 1.0  # kW @ -10°C
HEAT_PUMP_CONSUMPTION_MODEL = "Standard"  # Standard / Premium / Eco
HEATING_SEASON_ACTIVE = True       # Czy sezon grzewczy jest aktywny

# ==========================================================
# PARAMETRY UCZENIA (ADAPTACJA PLANU)
# ==========================================================
# Korekta celu SOC (w punktach procentowych) wyliczana z walidacji
# plan vs rzeczywistość. Aktualizowana automatycznie i utrwalana w DB.
LEARNING_SOC_TARGET_BIAS = 0.0


# ==========================================================
# FUNKCJE HELPER
# ==================================================

def get_house_load(hour: int) -> float:
    """
    Zwraca zużycie domu w kW dla danej godziny (0-23).
    """
    if hour < 6:
        return HOUSE_LOAD_PROFILE["night"]
    elif hour < 15:
        return HOUSE_LOAD_PROFILE["morning_day"]
    elif hour < 20:
        return HOUSE_LOAD_PROFILE["evening"]
    else:
        return HOUSE_LOAD_PROFILE["night_late"]


def is_cheap_tariff(hour: int) -> bool:
    """
    Zwraca True jeśli dana godzina jest w tanił taryfie.
    """
    for start, end in CHEAP_TARIFF_WINDOWS:
        if start < end:
            # Normalny przedział (np. 13-15)
            if start <= hour < end:
                return True
        else:
            # Przedział przechodzący przez północ (np. 22-6)
            if hour >= start or hour < end:
                return True
    return False
