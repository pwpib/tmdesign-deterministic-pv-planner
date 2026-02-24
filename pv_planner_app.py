import time as pytime

import logging
from datetime import datetime, timedelta, date, time
import appdaemon.plugins.hass.hassapi as hass

from pv_planner.snapshot import SnapshotReader
import pv_planner.planner_core as planner_core
from .plan_store import save_plan, mark_plan_executed
from .plan_reader import load_plan_for_today, load_plan_for_tomorrow, is_plan_executed
from .planner_executor import decide_execution
from .planner_executor import map_decision_to_action
from .ha_sync import ConfigSync


log = logging.getLogger(__name__)


class PVPlanner(hass.Hass):

    def initialize(self):
        # ===== SYNCHRONIZACJA PARAMETRÓW Z HA =====
        self.config_sync = ConfigSync(self)
        self.config_sync.load_all_from_ha()
        
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
                "target_soc": action.get("target_soc"),
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
                #"heat_pump_model": raw["heat_pump_model"],
                #"heat_pump_power_at_plus_5": raw["hp_power_plus_5"],
                #"heat_pump_power_at_0": raw["hp_power_0"],
                #"heat_pump_power_at_minus_5": raw["hp_power_minus_5"],
                #"heat_pump_power_at_minus_10": raw["hp_power_minus_10"],

                # podział energii
                #"energy_share_before_13": raw["energy_share_before_13"],
                #"energy_share_after_13": raw["energy_share_after_13"],

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
            self._send_programs_to_inverter(plan, inputs)

            tomorrow = date.fromordinal(date.today().toordinal() + 1).isoformat()
            mark_plan_executed(tomorrow)

            self.log("PV EXECUTOR Plan wysłany poprawnie")

        except Exception as e:
            self.log(f"PV EXECUTOR Blad wysylki: {e} retry za 5 min", level="ERROR")
            self.run_in(self._try_execute_plan, 300)

            self.log("PV EXECUTOR Plan wyslany poprawnie")

        except Exception as e:
            self.log(f"PV EXECUTOR Blad wysylki: {e} retry za 5 min", level="ERROR")
            self.run_in(self._try_execute_plan, 300)


    # ==========================================================
    # WYSYŁKA PROGRAMÓW
    # ==========================================================

    def _send_programs_to_inverter(self, plan, inputs):
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


