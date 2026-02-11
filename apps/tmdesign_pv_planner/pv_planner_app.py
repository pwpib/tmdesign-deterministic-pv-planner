import logging
from datetime import datetime, timedelta, date
import appdaemon.plugins.hass.hassapi as hass

from pv_planner.snapshot import SnapshotReader
import pv_planner.planner_core as planner_core
from .plan_store import save_plan, mark_plan_executed
from .plan_reader import load_plan_for_today, load_plan_for_tomorrow, is_plan_executed
from .planner_executor import decide_execution
from .planner_executor import map_decision_to_action


log = logging.getLogger(__name__)


class PVPlanner(hass.Hass):

    def initialize(self):
        plan_today = load_plan_for_today()
        self.log(f"PV PLANNER ▶ plan na dziś: {'ZNALEZIONY' if plan_today else 'BRAK'}")

        plan_tomorrow = load_plan_for_tomorrow()
        self.log(f"PV PLANNER ▶ plan na jutro: {'ZNALEZIONY' if plan_tomorrow else 'BRAK'}")

        executed = is_plan_executed(date.today().isoformat())
        self.log(f"PV PLANNER ▶ plan na dziś wykonany: {'TAK' if executed else 'NIE'}")

        if plan_today:
            decision = decide_execution(plan_today)
            self.log(f"PV PLANNER ▶ decyzja: {decision}")
        if plan_today:
            action = map_decision_to_action(decision)
            self.log(f"PV PLANNER ▶ akcja systemowa: {action}")

        if plan_today:
            inverter_payload = {
                "plan_date": plan_today.get("plan_date"),
                "grid_mode": action.get("grid_mode"),
                "target_soc": action.get("target_soc"),
                "night_charge_kwh": plan_today.get("night_charge_kwh"),
                "midday_charge_kwh": plan_today.get("midday_charge_kwh"),
                "reason": action.get("reason")
            }

            self.log(f"PV PLANNER ▶ FALOWNIK PAYLOAD (DRY-RUN): {inverter_payload}")

        # ===== ETAP 4 - WYKONANIE PLANU (DZIŚ) =====
        if plan_today and not executed:
            self.log("PV PLANNER ▶ wykonuję plan na dziś")

            # TU W PRZYSZŁOŚCI BĘDZIE STEROWANIE FALOWNIKIEM
            # (SOC + Grid/Disabled)

            mark_plan_executed(date.today().isoformat())
            self.log("PV PLANNER ▶ plan oznaczony jako wykonany")

            log.info("PV PLANNER ▶ start appki")

        self.listen_state(
            self._on_test_trigger,
            "input_boolean.pv_planner_test_trigger",
            new="on"
        )

        log.info("PV PLANNER ▶ gotowy (czeka na trigger)")

    def _on_test_trigger(self, entity, attribute, old, new, kwargs):
        log.info("PV PLANNER ▶ TRIGGER: snapshot")

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
                "heat_pump_model": raw["heat_pump_model"],
                "heat_pump_power_at_plus_5": raw["hp_power_plus_5"],
                "heat_pump_power_at_0": raw["hp_power_0"],
                "heat_pump_power_at_minus_5": raw["hp_power_minus_5"],
                "heat_pump_power_at_minus_10": raw["hp_power_minus_10"],

                # podział energii
                "energy_share_before_13": raw["energy_share_before_13"],
                "energy_share_after_13": raw["energy_share_after_13"],

                # bateria
                "battery_energy_now_kwh": raw["battery_energy_kwh"],
                "battery_capacity_kwh": raw["battery_capacity_kwh"],
                "battery_soc_min_winter": raw["soc_min_winter"],
                "battery_soc_min_summer": raw["soc_min_summer"],
                "battery_soc_max": raw["soc_max"],

                # pv
                "pv_forecast_tomorrow": raw["pv_forecast_tomorrow"],

            }

            log.info(f"PV PLANNER ▶ plan_date: {snapshot['plan_date']}")

            # ===== ETAP 2 – PLANOWANIE =====
            plan = planner_core.run(snapshot)
            log.info("PV PLANNER ▶ plan obliczony (D+1)")

            save_plan(plan["plan_date"], plan, snapshot)

        except Exception as e:
            log.error(f"PV PLANNER ▶ BŁĄD: {e}", exc_info=True)

        finally:
            # reset triggera ZAWSZE
            self.call_service(
                "input_boolean/turn_off",
                entity_id="input_boolean.pv_planner_test_trigger"
            )
