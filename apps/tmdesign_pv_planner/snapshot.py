print("=== SNAPSHOT FILE VERSION B ===")
import sqlite3
import json
from datetime import datetime


class SnapshotReader:
    """
    PLIK 1 – SNAPSHOT
    - Odczyt encji z Home Assistant
    - Walidacja typów
    - Zapis do bazy (SQLite)
    - ZERO logiki biznesowej
    """

    def __init__(self, hass, db_path):
        self.hass = hass
        self.db_path = db_path

    # -------------------------------------------------
    # NARZĘDZIA
    # -------------------------------------------------

    def _get_state(self, entity_id):
        state = self.hass.get_state(entity_id)
        if state is None:
            self.hass.log(f"SNAPSHOT ❌ brak encji: {entity_id}", level="ERROR")
        return state

    def _to_float(self, entity_id):
        try:
            return float(self._get_state(entity_id))
        except (TypeError, ValueError):
            self.hass.log(f"SNAPSHOT ❌ float error: {entity_id}", level="ERROR")
            return None

    def _to_int(self, entity_id):
        try:
            return int(float(self._get_state(entity_id)))
        except (TypeError, ValueError):
            self.hass.log(f"SNAPSHOT ❌ int error: {entity_id}", level="ERROR")
            return None

    def _to_bool(self, entity_id):
        state = self._get_state(entity_id)
        if state in ("on", "true", "True", True):
            return True
        if state in ("off", "false", "False", False):
            return False
        self.hass.log(f"SNAPSHOT ❌ bool error: {entity_id}", level="ERROR")
        return None

    def _to_str(self, entity_id):
        return str(self._get_state(entity_id))

    # -------------------------------------------------
    # GŁÓWNY SNAPSHOT
    # -------------------------------------------------

    def read_snapshot(self):
        self.hass.log("SNAPSHOT ▶️ rozpoczęcie sczytywania encji")

        snapshot = {
            "timestamp": datetime.now().isoformat(),

            # --- POGODA ---
            "temperature_tomorrow_avg": self._to_float("sensor.open_meteo_temperature_tomorrow_avg"),
            "season_temperature_threshold": self._to_float("input_number.season_temperature_threshold"),
            "heating_season_active": self._to_bool("input_boolean.heating_season_active"),
            "summer_season_active": self._to_bool("input_boolean.summer_season_active"),

            # --- MODEL POMPY ---
            "heat_pump_model": self._to_str("input_select.heat_pump_consumption_model"),
            "hp_power_plus_5": self._to_float("input_number.heat_pump_power_at_plus_5"),
            "hp_power_0": self._to_float("input_number.heat_pump_power_at_0"),
            "hp_power_minus_5": self._to_float("input_number.heat_pump_power_at_minus_5"),
            "hp_power_minus_10": self._to_float("input_number.heat_pump_power_at_minus_10"),

            # --- PODZIAŁ ENERGII ---
            "energy_share_before_13": self._to_float("input_number.energy_share_before_13"),
            "energy_share_after_13": self._to_float("input_number.energy_share_after_13"),

            # --- MAGAZYN ---
            "battery_energy_kwh": self._to_float("input_number.inverter_battery_energy"),
            "soc_current_percent": self._to_float("input_number.inverter_battery_soc"),
            "battery_soc": self._to_float("input_number.inverter_battery_soc"),
            "battery_capacity_kwh": self._to_float("input_number.battery_capacity_kwh"),
            "soc_min_winter": self._to_float("input_number.battery_soc_min_winter"),
            "soc_min_summer": self._to_float("input_number.battery_soc_min_summer"),
            "soc_max": self._to_float("input_number.battery_soc_max"),

            # --- PV ---
            "pv_forecast_tomorrow": self._to_float("sensor.energy_production_tomorrow"),

            # --- ASTRONOMIA ---
            "sun_next_dawn": self._to_str("sensor.sun_next_dawn"),
            "sun_next_dusk": self._to_str("sensor.sun_next_dusk"),

            # --- TARYFY ---
            "tariff_night": self._to_bool("input_boolean.tariff_night"),
            "tariff_morning_day": self._to_bool("input_boolean.tariff_morning_day"),
            "tariff_midday": self._to_bool("input_boolean.tariff_midday"),
            "tariff_evening_day": self._to_bool("input_boolean.tariff_evening_day"),

            # --- STEROWANIE ---
            "planner_enabled": self._to_bool("input_boolean.pv_planner_enabled"),
            "planner_executed_today": self._to_bool("input_boolean.pv_planner_executed_today"),
            "planner_run_mode": self._to_str("input_select.pv_planner_run_mode"),
            "planner_ready": self._to_bool("input_boolean.pv_planner_ready_for_run"),

            # --- CZAS ---
            "time": self._to_str("sensor.time"),
            "date": self._to_str("sensor.date"),
            "soc_current_percent": self._to_float("input_number.inverter_battery_soc"),


        }

        self._save_snapshot(snapshot)
        self.hass.log("SNAPSHOT ✅ zapis zakończony")

        return snapshot

    # -------------------------------------------------
    # BAZA DANYCH
    # -------------------------------------------------

    def _save_snapshot(self, snapshot):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                data TEXT
            )
        """)

        cur.execute(
            "INSERT INTO snapshots (timestamp, data) VALUES (?, ?)",
            (snapshot["timestamp"], json.dumps(snapshot))
        )

        conn.commit()
        conn.close()
