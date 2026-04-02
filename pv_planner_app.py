import time as pytime

import logging
from datetime import datetime, timedelta, date, time
import appdaemon.plugins.hass.hassapi as hass

from pv_planner.snapshot import SnapshotReader
import pv_planner.planner_core as planner_core
from .plan_store import (
    save_plan,
    mark_plan_executed,
    save_plan_validation,
    get_learning_state,
    set_learning_state,
)
from .plan_reader import load_plan_for_today, load_plan_for_tomorrow, is_plan_executed
from .planner_executor import decide_execution
from .planner_executor import map_decision_to_action
from .ha_sync import ConfigSync
from . import config


log = logging.getLogger(__name__)


class PVPlanner(hass.Hass):

    def initialize(self):
        # ===== SYNCHRONIZACJA PARAMETRÓW Z HA =====
        self.config_sync = ConfigSync(self)
        self.config_sync.load_all_from_ha()
        current_bias = get_learning_state("soc_target_bias", 0.0)
        config.LEARNING_SOC_TARGET_BIAS = current_bias
        self.log(f"PV LEARNING zaladowany bias SOC: {current_bias:+.2f} pp")
        
        # ===== RESZTA APLIKACJI =====
        plan_today = load_plan_for_today()
        self.log(f"PV PLANNER  plan na dzis: {'ZNALEZIONY' if plan_today else 'BRAK'}")

        plan_tomorrow = load_plan_for_tomorrow()
        self.log(f"PV PLANNER  plan na jutro: {'ZNALEZIONY' if plan_tomorrow else 'BRAK'}")

        executed = is_plan_executed(date.today().isoformat())
        self.log(f"PV PLANNER  plan na dzis wykonany: {'TAK' if executed else 'NIE'}")

        if plan_today:
            decision = decide_execution(plan_today)
            self.log(f"PV PLANNER  decyzja: {decision}")
        if plan_today:
            action = map_decision_to_action(decision)
            self.log(f"PV PLANNER  akcja systemowa: {action}")

        if plan_today:
            inverter_payload = {
                "plan_date": plan_today.get("plan_date"),
                "grid_allowed": action.get("grid_allowed"),
                "target_soc": action.get("target_soc_percent"),
                "night_charge_kwh": plan_today.get("night_charge_kwh"),
                "midday_charge_kwh": plan_today.get("midday_charge_kwh"),
                "reason": action.get("reason")
            }

            self.log(f"PV PLANNER  FALOWNIK PAYLOAD (DRY-RUN): {inverter_payload}")

        # ===== ETAP 4 - WYKONANIE PLANU (DZIŚ) =====
        if plan_today and not executed:
            self.log("PV PLANNER  wykonuje plan na dzis")

            # TU W PRZYSZŁOŚCI BĘDZIE STEROWANIE FALOWNIKIEM
            # (SOC + Grid/Disabled)

            mark_plan_executed(date.today().isoformat())
            self.log("PV PLANNER  plan oznaczony jako wykonany")

            log.info("PV PLANNER  start appki")

        self.listen_state(
            self._on_test_trigger,
            "input_boolean.pv_planner_test_trigger",
            new="on"
        )
        # ===== AUTO PLAN 21:50 ======
        self.run_daily(self._auto_plan, time(21, 50))
        self.log("PV PLANNER  rejestruje auto-plan 21:50")

        # ===== EXECUTOR 22:00 ======
        self.log("PV PLANNER  rejestruje executor 22:00")
        self.run_daily(self._start_executor, time(22, 0))

        #--------------------------------------------------------------------------------
        # ===== TEST EXECUTORA po 10 sekundach od startu (usuń po teście) =====
        #self.run_in(self._start_executor, 10)
        #-------------------------------------------------------------------------------

        log.info("PV PLANNER  gotowy (czeka na trigger)")

    def _on_test_trigger(self, entity, attribute, old, new, kwargs):
        log.info("PV PLANNER  TRIGGER: snapshot")

        try:
            # ===== ETAP 1 – SNAPSHOT =====
            reader = SnapshotReader(
                self,
                "/config/apps/pv_planner/data/snapshots.db"
            )
            raw = reader.read_snapshot()
            self._validate_today_plan_and_update_learning(raw)

            # ===== NORMALIZACJA SNAPSHOTU (INTERFEJS) =====
            snapshot = {
                # data planu D+1
                "plan_date": (
                    datetime.strptime(raw["date"], "%Y-%m-%d").date()
                    + timedelta(days=1)
                ).isoformat(),

                # temperatura
                "temp_avg_tomorrow": raw["temperature_tomorrow_avg"],
                "season_temperature_threshold": raw["season_temperature_threshold"],

                # --- ASTRONOMIA ---
                "sun_next_dawn": raw["sun_next_dawn"],
                "sun_next_dusk": raw["sun_next_dusk"],

                # sezon
                "heating_season_active": raw["heating_season_active"],
                "summer_season_active": raw["summer_season_active"],

                # model pompy
                "heat_pump_model": raw["heat_pump_model"],
                "heat_pump_power_at_plus_15": raw["hp_power_plus_15"],
                "heat_pump_power_at_plus_10": raw["hp_power_plus_10"],
                "heat_pump_power_at_plus_5": raw["hp_power_plus_5"],
                "heat_pump_power_at_0": raw["hp_power_0"],
                "heat_pump_power_at_minus_5": raw["hp_power_minus_5"],
                "heat_pump_power_at_minus_10": raw["hp_power_minus_10"],

                # podział energii
                "energy_share_before_13": (
                    float(raw["energy_share_before_13"]) / 100.0
                    if raw.get("energy_share_before_13") is not None
                    else None
                ),
                "energy_share_after_13": (
                    float(raw["energy_share_after_13"]) / 100.0
                    if raw.get("energy_share_after_13") is not None
                    else None
                ),

                # bateria
                "battery_soc_now": float(self.get_state("sensor.inverter_battery")),
                "battery_capacity_kwh": raw["battery_capacity_kwh"],
                "battery_soc_min_winter": raw["soc_min_winter"],
                "battery_soc_min_summer": raw["soc_min_summer"],
                "battery_soc_max": raw["soc_max"],

                # pv
                "pv_forecast_tomorrow": raw["pv_forecast_tomorrow"],

            }

            log.info(f"PV PLANNER  plan_date: {snapshot['plan_date']}")

            # ===== ETAP 2 – PLANOWANIE =====
            plan = planner_core.run(snapshot)
            log.info("PV PLANNER plan obliczony (D+1)")

            save_plan(plan["plan_date"], plan, snapshot)

        except Exception as e:
            log.error(f"PV PLANNER BŁAD: {e}", exc_info=True)

        finally:
            # reset triggera ZAWSZE
            self.call_service(
                "input_boolean/turn_off",
                entity_id="input_boolean.pv_planner_test_trigger"
            )

    def _validate_today_plan_and_update_learning(self, raw: dict):
        """
        Waliduje plan na DZISIAJ (D) na podstawie bieżących pomiarów i
        aktualizuje prosty parametr uczenia: bias celu SOC.
        """
        today_wrapper = load_plan_for_today()
        if not today_wrapper:
            self.log("PV LEARNING brak planu na dzis - walidacja pominięta")
            return

        plan = today_wrapper.get("plan", {})
        if not isinstance(plan, dict):
            self.log("PV LEARNING niepoprawna struktura planu - walidacja pominięta", level="WARNING")
            return

        target_soc = plan.get("target_soc_percent")
        actual_soc = raw.get("soc_current_percent")
        grid_import_today = raw.get("grid_import_today_kwh")
        grid_export_today = raw.get("grid_export_today_kwh")

        if target_soc is None or actual_soc is None:
            self.log("PV LEARNING brak target/actual SOC - walidacja pominięta", level="WARNING")
            return

        soc_error = float(actual_soc) - float(target_soc)
        plan_date = date.today().isoformat()

        validation_payload = {
            "plan_date": plan_date,
            "target_soc_percent": float(target_soc),
            "actual_soc_percent": float(actual_soc),
            "soc_error_percent_points": soc_error,
            "grid_import_today_kwh": grid_import_today,
            "grid_export_today_kwh": grid_export_today,
        }
        save_plan_validation(plan_date, validation_payload)

        old_bias = get_learning_state("soc_target_bias", 0.0)
        learning_rate = 0.20
        new_bias = old_bias + (-soc_error * learning_rate)
        new_bias = max(-15.0, min(15.0, new_bias))

        set_learning_state("soc_target_bias", new_bias)
        config.LEARNING_SOC_TARGET_BIAS = new_bias

        self.log(
            f"PV LEARNING walidacja D: target={target_soc:.1f} actual={actual_soc:.1f} "
            f"error={soc_error:+.2f}pp bias: {old_bias:+.2f} -> {new_bias:+.2f}"
        )

    # ==========================================================
    # AUTO PLAN 21:50
    # ==========================================================
    def _auto_plan(self, kwargs):
        self.log("PV PLANNER AUTO PLAN START")
        try:
            plan_tomorrow = load_plan_for_tomorrow()
            if plan_tomorrow:
                self.log("PV PLANNER  plan na jutro juz istnieje pomijam")
                return
            self._on_test_trigger(None, None, None, "on", {})
            self.log("PV PLANNER AUTO PLAN ZAKONCZONY")
        except Exception as e:
            self.log(f"PV PLANNER  AUTO PLAN BLAD: {e}", level="ERROR")
    
    # ==========================================================
    # EXECUTOR 22:00
    # ==========================================================

    def _start_executor(self, kwargs):
        self.log("PV EXECUTOR  22:00 start")

        self.executor_deadline = self.datetime().replace(hour=6, minute=0, second=0)
        if self.executor_deadline < self.datetime():
            self.executor_deadline = self.executor_deadline + timedelta(days=1)

        self._try_execute_plan({})


    def _try_execute_plan(self, kwargs):
        now = self.datetime()

        if now >= self.executor_deadline:
            self.log("PV EXECUTOR Deadline 06:00 osiągniety przerywam", level="WARNING")
            return

        plan_wrapper = load_plan_for_tomorrow()

        self.log(f"PV EXECUTOR PLAN RAW: {plan_wrapper}")

        if not plan_wrapper:
            self.log("PV EXECUTOR Brak planu retry za 5 min", level="WARNING")
            self.run_in(self._try_execute_plan, 300)
            return

        plan = plan_wrapper.get("plan")
        inputs = plan_wrapper.get("inputs")

        if not plan or not inputs:
            self.log("PV EXECUTOR Bledna struktura planu retry za 5 min", level="ERROR")
            self.run_in(self._try_execute_plan, 300)
            return

        try:
            self._validate_plan_before_inverter_send(plan, inputs)
            self._send_programs_to_inverter(plan)

            tomorrow = date.fromordinal(date.today().toordinal() + 1).isoformat()
            mark_plan_executed(tomorrow)

            self.log("PV EXECUTOR Plan wysłany poprawnie")

        except Exception as e:
            self.log(f"PV EXECUTOR Blad wysylki: {e} retry za 5 min", level="ERROR")
            self.run_in(self._try_execute_plan, 300)


    # ==========================================================
    # WYSYŁKA PROGRAMÓW
    # ==========================================================

    def _validate_plan_before_inverter_send(self, plan: dict, inputs: dict) -> None:
        required_keys = {"programs", "pv_start_time", "pv_end_time"}
        missing = [k for k in required_keys if k not in plan]
        if missing:
            raise ValueError(f"Brak wymaganych pol planu: {missing}")

        programs = plan.get("programs")
        if not isinstance(programs, list) or len(programs) != 6:
            raise ValueError(f"Niepoprawna lista programow: oczekiwano 6, otrzymano {len(programs) if isinstance(programs, list) else 'nie-lista'}")

        season = str(plan.get("season", "")).lower()
        soc_max_cfg = inputs.get("battery_soc_max")
        soc_min_winter_cfg = inputs.get("battery_soc_min_winter")
        soc_min_summer_cfg = inputs.get("battery_soc_min_summer")

        if soc_max_cfg is None:
            raise ValueError("Brak battery_soc_max w inputs planu")
        soc_max = int(float(soc_max_cfg))
        if soc_max <= 0 or soc_max > 100:
            raise ValueError(f"Niepoprawny battery_soc_max: {soc_max}")

        if season == "winter":
            if soc_min_winter_cfg is None:
                raise ValueError("Brak battery_soc_min_winter w inputs planu")
            soc_min = int(float(soc_min_winter_cfg))
        else:
            if soc_min_summer_cfg is None:
                raise ValueError("Brak battery_soc_min_summer w inputs planu")
            soc_min = int(float(soc_min_summer_cfg))

        if soc_min <= 0:
            raise ValueError(f"Niepoprawny minimalny SOC dla sezonu {season or 'summer'}: {soc_min}")
        if soc_min >= soc_max:
            raise ValueError(f"Niepoprawny zakres SOC: min={soc_min}, max={soc_max}")

        controlled_soc_programs = {1, 4}
        non_controlled_soc_programs = {2, 3, 5, 6}

        for p in programs:
            if "program" not in p or "soc" not in p:
                raise ValueError(f"Niepoprawna struktura programu: {p}")
            nr = int(p["program"])
            soc = int(p["soc"])
            if nr < 1 or nr > 6:
                raise ValueError(f"Niepoprawny numer programu: {nr}")
            if soc < soc_min or soc > soc_max:
                raise ValueError(f"SOC poza zakresem {soc_min}-{soc_max} dla programu {nr}: {soc}")
            if nr in non_controlled_soc_programs and soc != soc_min:
                raise ValueError(f"Program {nr} nie podlega sterowaniu SOC i musi miec wartosc minimalna {soc_min}, otrzymano {soc}")
            if nr not in controlled_soc_programs and nr not in non_controlled_soc_programs:
                raise ValueError(f"Program {nr} nie ma zdefiniowanej polityki sterowania")

        def _parse_clock(label: str, value: str) -> datetime:
            try:
                return datetime.strptime(value, "%H:%M:%S")
            except Exception as exc:
                raise ValueError(f"Niepoprawny format czasu {label}: {value} (oczekiwano HH:MM:SS)") from exc

        p3 = _parse_clock("pv_start_time", plan["pv_start_time"])
        p6 = _parse_clock("pv_end_time", plan["pv_end_time"])
        if p6 <= p3:
            raise ValueError(f"Niepoprawne okno PV: pv_end_time ({plan['pv_end_time']}) <= pv_start_time ({plan['pv_start_time']})")

        p3_limit = datetime.strptime(f"{config.PROGRAM_3_EARLIEST_HOUR:02d}:{config.PROGRAM_3_EARLIEST_MIN:02d}:00", "%H:%M:%S")
        p6_limit = datetime.strptime(f"{config.PROGRAM_6_EARLIEST_HOUR:02d}:{config.PROGRAM_6_EARLIEST_MIN:02d}:00", "%H:%M:%S")
        if p3 < p3_limit:
            raise ValueError(f"Program 3 startuje zbyt wcześnie: {plan['pv_start_time']} < {p3_limit.strftime('%H:%M:%S')}")
        if p6 < p6_limit:
            raise ValueError(f"Program 6 startuje zbyt wcześnie: {plan['pv_end_time']} < {p6_limit.strftime('%H:%M:%S')}")

    def _send_programs_to_inverter(self, plan):
        programs = plan["programs"]

        pv_start = plan["pv_start_time"]
        pv_end = plan["pv_end_time"]

        times = {
            1: "00:00:00",
            2: "06:00:00",
            3: pv_start,
            4: "13:00:00",
            5: "15:00:00",
            6: pv_end
        }

        for program in programs:
            nr = program["program"]
            soc = int(program["soc"])

            self.log(f"PV EXECUTOR Ustawiam program {nr}")

            # --- CZAS ---
            self.call_service(
                "time/set_value",
                entity_id=f"time.inverter_program_{nr}_time",
                time=times[nr]
            )

            pytime.sleep(0.3)

            # --- SOC ---
            self.call_service(
                "number/set_value",
                entity_id=f"number.inverter_program_{nr}_soc",
                value=soc
            )

            # czekamy aż SOC faktycznie się zmieni
            for _ in range(5):
                pytime.sleep(0.3)
                current_soc = self.get_state(f"number.inverter_program_{nr}_soc")
                if str(current_soc) == str(soc):
                    break
            else:
                raise Exception(f"SOC programu {nr} nie zostal ustawiony")

            self.log(f"Program {nr} OK: {times[nr]} | SOC {soc}%")
