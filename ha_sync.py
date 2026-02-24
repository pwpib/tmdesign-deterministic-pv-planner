"""
PV Planner - Moduł integracji Home Assistant

Funkcje do synchronizacji parametrów między Home Assistant a aplikacją.
"""

import logging

log = logging.getLogger(__name__)


class ConfigSync:
    """
    Synchronizuje parametry z Home Assistant do aplikacji.
    Umożliwia zmianę parametrów bez restartu aplikacji.
    """

    def __init__(self, hass_api):
        """
        Inicjalizuj synchronizator konfiguracji.
        
        Args:
            hass_api: self z AppDaemon.Hass
        """
        self.hass = hass_api
        self._listen_for_changes()

    def _listen_for_changes(self):
        """Zarejstruj nasłuchiwanie zmian parametrów."""
        
        # Współczynniki PV
        self.hass.listen_state(
            self._on_pv_ratio_change,
            "input_number.pv_planner_pv_before_13_ratio"
        )
        self.hass.listen_state(
            self._on_pv_ratio_change,
            "input_number.pv_planner_pv_after_13_ratio"
        )
        
        # Offsety czasowe słońca
        self.hass.listen_state(
            self._on_sun_offset_change,
            "input_number.pv_planner_pv_dawn_offset_min"
        )
        self.hass.listen_state(
            self._on_sun_offset_change,
            "input_number.pv_planner_pv_dusk_offset_min"
        )
        
        # Limity czasowe programów
        self.hass.listen_state(
            self._on_program_limit_change,
            [
                "input_text.pv_planner_program_3_earliest_time",
                "input_text.pv_planner_program_6_earliest_time",
            ]
        )
        
        # Profile zużycia domu
        self.hass.listen_state(
            self._on_house_load_change,
            [
                "input_number.pv_planner_house_load_night",
                "input_number.pv_planner_house_load_morning_day",
                "input_number.pv_planner_house_load_evening",
                "input_number.pv_planner_house_load_night_late",
            ]
        )
        
        # Taryfy
        self.hass.listen_state(
            self._on_tariff_change,
            "input_select.pv_planner_cheap_tariff_windows"
        )
        
        # Pompa ciepła
        self.hass.listen_state(
            self._on_heat_pump_change,
            [
                "input_number.pv_planner_heat_pump_power_at_plus_15",
                "input_number.pv_planner_heat_pump_power_at_plus_10",
                "input_number.pv_planner_heat_pump_power_at_plus_5",
                "input_number.pv_planner_heat_pump_power_at_0",
                "input_number.pv_planner_heat_pump_power_at_minus_5",
                "input_number.pv_planner_heat_pump_power_at_minus_10",
                "input_select.pv_planner_heat_pump_consumption_model",
                "input_boolean.pv_planner_heating_season_active",
            ]
        )
        
        self.hass.log("PV PLANNER Synchronizacja parametrow HA wlaczona")

    def _on_pv_ratio_change(self, entity, attribute, old, new, kwargs):
        """Obsłuż zmianę współczynników PV."""
        try:
            from . import config
            
            before_13 = float(self.hass.get_state(
                "input_number.pv_planner_pv_before_13_ratio"
            )) / 100.0
            after_13 = float(self.hass.get_state(
                "input_number.pv_planner_pv_after_13_ratio"
            )) / 100.0
            
            config.PV_BEFORE_13_RATIO = before_13
            config.PV_AFTER_13_RATIO = after_13
            
            # Aktualizuj także w planner_core
            import pv_planner.planner_core as planner_core
            planner_core.PV_BEFORE_13_RATIO = before_13
            planner_core.PV_AFTER_13_RATIO = after_13
            
            self.hass.log(
                f"PV PLANNER Wspolczynniki PV: {before_13:.2f}/{after_13:.2f}"
            )
        except Exception as e:
            self.hass.log(f"PV PLANNER Blad aktualizacji wspolczynnikow: {e}", level="ERROR")

    def _on_sun_offset_change(self, entity, attribute, old, new, kwargs):
        """Obsłuż zmianę offsetów czasowych słońca."""
        try:
            from . import config
            
            dawn_offset = int(float(self.hass.get_state(
                "input_number.pv_planner_pv_dawn_offset_min"
            )))
            dusk_offset = int(float(self.hass.get_state(
                "input_number.pv_planner_pv_dusk_offset_min"
            )))
            
            config.PV_DAWN_OFFSET_MIN = dawn_offset
            config.PV_DUSK_OFFSET_MIN = dusk_offset
            
            # Aktualizuj także w planner_core
            import pv_planner.planner_core as planner_core
            planner_core.PV_DAWN_OFFSET_MIN = dawn_offset
            planner_core.PV_DUSK_OFFSET_MIN = dusk_offset
            
            self.hass.log(
                f"PV PLANNER Offsety slonca: dawn={dawn_offset}min, dusk={dusk_offset}min"
            )
        except Exception as e:
            self.hass.log(f"PV PLANNER Blad aktualizacji offsetow: {e}", level="ERROR")

    def _on_program_limit_change(self, entity, attribute, old, new, kwargs):
        """Obsłuż zmianę limitów czasowych programów."""
        try:
            from . import config
            
            p3_time = self.hass.get_state(
                "input_text.pv_planner_program_3_earliest_time"
            )
            p6_time = self.hass.get_state(
                "input_text.pv_planner_program_6_earliest_time"
            )
            
            # Parsuj czas w formacie HH:MM
            if p3_time and ':' in p3_time:
                p3_parts = p3_time.split(':')
                p3_hour = int(p3_parts[0])
                p3_min = int(p3_parts[1])
                config.PROGRAM_3_EARLIEST_HOUR = p3_hour
                config.PROGRAM_3_EARLIEST_MIN = p3_min
            
            if p6_time and ':' in p6_time:
                p6_parts = p6_time.split(':')
                p6_hour = int(p6_parts[0])
                p6_min = int(p6_parts[1])
                config.PROGRAM_6_EARLIEST_HOUR = p6_hour
                config.PROGRAM_6_EARLIEST_MIN = p6_min
            
            if p3_time and ':' in p3_time and p6_time and ':' in p6_time:
                self.hass.log(
                    f"PV PLANNER Limity programow: P3={p3_time}, P6={p6_time}"
                )
        except Exception as e:
            self.hass.log(f"PV PLANNER Blad aktualizacji limitow: {e}", level="ERROR")

    def _on_house_load_change(self, entity, attribute, old, new, kwargs):
        """Obsłuż zmianę profilu zużycia domu."""
        try:
            from . import config
            
            night = float(self.hass.get_state(
                "input_number.pv_planner_house_load_night"
            ))
            morning_day = float(self.hass.get_state(
                "input_number.pv_planner_house_load_morning_day"
            ))
            evening = float(self.hass.get_state(
                "input_number.pv_planner_house_load_evening"
            ))
            night_late = float(self.hass.get_state(
                "input_number.pv_planner_house_load_night_late"
            ))
            
            config.HOUSE_LOAD_PROFILE["night"] = night
            config.HOUSE_LOAD_PROFILE["morning_day"] = morning_day
            config.HOUSE_LOAD_PROFILE["evening"] = evening
            config.HOUSE_LOAD_PROFILE["night_late"] = night_late
            
            self.hass.log(
                f"PV PLANNER Profile domu: noc={night}kW, dzien={morning_day}kW, "
                f"wieczor={evening}kW, pozna_noc={night_late}kW"
            )
        except Exception as e:
            self.hass.log(f"PV PLANNER Blad aktualizacji profilu domu: {e}", level="ERROR")

    def _on_tariff_change(self, entity, attribute, old, new, kwargs):
        """Obsłuż zmianę taryf prądowych."""
        try:
            from . import config
            
            tariff_option = self.hass.get_state("input_select.pv_planner_cheap_tariff_windows")
            
            # Mapuj opcję na okna taryf
            tariff_map = {
                "Noc (22-6h) + Midday (13-15h)": [(22, 6), (13, 15)],
                "Noc (22-6h) + Popołudnie (14-16h)": [(22, 6), (14, 16)],
                "Noc (23-6h)": [(23, 6)],
            }
            
            if tariff_option in tariff_map:
                config.CHEAP_TARIFF_WINDOWS = tariff_map[tariff_option]
                self.hass.log(f"PV PLANNER Taryfy: {tariff_option}")
            else:
                self.hass.log(
                    f"PV PLANNER Nieznana opcja taryfy: {tariff_option}",
                    level="WARNING"
                )
        except Exception as e:
            self.hass.log(f"PV PLANNER Blad aktualizacji taryf: {e}", level="ERROR")

    def _on_heat_pump_change(self, entity, attribute, old, new, kwargs):
        """Obsłuż zmianę parametrów pompy ciepła."""
        try:
            from . import config
            
            hp_plus_15 = float(self.hass.get_state(
                "input_number.pv_planner_heat_pump_power_at_plus_15"
            ))
            hp_plus_10 = float(self.hass.get_state(
                "input_number.pv_planner_heat_pump_power_at_plus_10"
            ))
            hp_plus_5 = float(self.hass.get_state(
                "input_number.pv_planner_heat_pump_power_at_plus_5"
            ))
            hp_0 = float(self.hass.get_state(
                "input_number.pv_planner_heat_pump_power_at_0"
            ))
            hp_minus_5 = float(self.hass.get_state(
                "input_number.pv_planner_heat_pump_power_at_minus_5"
            ))
            hp_minus_10 = float(self.hass.get_state(
                "input_number.pv_planner_heat_pump_power_at_minus_10"
            ))
            hp_model = self.hass.get_state(
                "input_select.pv_planner_heat_pump_consumption_model"
            )
            heating_active = self.hass.get_state(
                "input_boolean.pv_planner_heating_season_active"
            ) == "on"
            
            config.HEAT_PUMP_POWER_AT_PLUS_15 = hp_plus_15
            config.HEAT_PUMP_POWER_AT_PLUS_10 = hp_plus_10
            config.HEAT_PUMP_POWER_AT_PLUS_5 = hp_plus_5
            config.HEAT_PUMP_POWER_AT_0 = hp_0
            config.HEAT_PUMP_POWER_AT_MINUS_5 = hp_minus_5
            config.HEAT_PUMP_POWER_AT_MINUS_10 = hp_minus_10
            config.HEAT_PUMP_CONSUMPTION_MODEL = hp_model
            config.HEATING_SEASON_ACTIVE = heating_active
            
            self.hass.log(
                f"PV PLANNER Pompa ciepla: +15sC={hp_plus_15}kW, +10sC={hp_plus_10}kW, "
                f"+5sC={hp_plus_5}kW, 0sC={hp_0}kW, -5sC={hp_minus_5}kW, -10sC={hp_minus_10}kW, "
                f"model={hp_model}, sezon_grzewczy={heating_active}"
            )
        except Exception as e:
            self.hass.log(f"PV PLANNER Blad aktualizacji pompy ciepla: {e}", level="ERROR")

    def load_all_from_ha(self):
        """
        Wczytaj wszystkie parametry z HA jednorazowo.
        Przydatne przy starcie aplikacji.
        """
        self._on_pv_ratio_change(None, None, None, None, {})
        self._on_sun_offset_change(None, None, None, None, {})
        self._on_program_limit_change(None, None, None, None, {})
        self._on_house_load_change(None, None, None, None, {})
        self._on_tariff_change(None, None, None, None, {})
        self._on_heat_pump_change(None, None, None, None, {})
        
        self.hass.log("PV PLANNER Wszystkie parametry zaladowane z HA")
