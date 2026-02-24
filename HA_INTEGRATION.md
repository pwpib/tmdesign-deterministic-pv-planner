# Integracja Home Assistant - Instrukcja

## 1. Zainstaluj plik konfiguracji HA

Skopiuj zawartość `homeassistant_config.yaml` do swojego `configuration.yaml`:

```yaml
# W configuration.yaml lub osobnym pliku yang zaimportuje

input_number:
  pv_planner_pv_before_13_ratio:
    name: "PV Planner: Udział energii PV przed 13:00"
    unit_of_measurement: "%"
    min: 30
    max: 70
    step: 5
  # ... (pozostałe parametry z homeassistant_config.yaml)

input_select:
  pv_planner_cheap_tariff_windows:
    name: "PV Planner: Okna tanich taryf"
    options:
      - "Noc (22-6h) + Midday (13-15h)"
      - "Noc (22-6h) + Popołudnie (14-16h)"
      - "Noc (23-6h)"
```

## 2. Restart Home Assistant

Wejdź w Developer Tools → YAML → Restart Home Assistant

## 3. Zweryfikuj encje

Settings → Devices & Services → Helpers

Powinna być dostępne encje `input_number.pv_planner_*` itp.

## 4. Integracja z AppDaemon

Dodaj ten kod do `pv_planner_app.py` funkcji `initialize()`:

```python
from .ha_sync import ConfigSync

class PVPlanner(hass.Hass):

    def initialize(self):
        # ... istniejący kod ...
        
        # ===== SYNCHRONIZACJA PARAMETRÓW Z HA =====
        self.config_sync = ConfigSync(self)
        self.config_sync.load_all_from_ha()
        
        # ===== REST APLIKACJI =====
        # ... reszta initialize() ...
```

## 5. Test

1. Przejdź do **Settings → Devices & Services → Helpers**
2. Zmień wartość któregoś suwaka (np. `pv_planner_pv_before_13_ratio` na 65%)
3. Sprawdź logi AppDaemon:

```
PV PLANNER ▶ Współczynniki PV: 0.65/0.35
```

## 📊 Przepływ danych

```
┌──────────────────────────────────────────────────┐
│         Home Assistant UI                         │
│  (Settings → Devices & Services → Helpers)       │
│                                                  │
│  input_number.pv_planner_pv_before_13_ratio     │
│  [████████████████░░░░░░] 65%                    │
└──────────────────────────────────────────────────┘
                      │ State Change
                      ↓
┌──────────────────────────────────────────────────┐
│  AppDaemon: ConfigSync.listen_state()            │
│  _on_pv_ratio_change() wyzwolony                │
└──────────────────────────────────────────────────┘
                      │ Update Config
                      ↓
┌──────────────────────────────────────────────────┐
│  config.py                                       │
│  PV_BEFORE_13_RATIO = 0.65  ← ZMIENIONE         │
│  PV_AFTER_13_RATIO = 0.35   ← AUTOMATYCZNIE     │
└──────────────────────────────────────────────────┘
                      │ Use New Values
                      ↓
┌──────────────────────────────────────────────────┐
│  planner_core.py                                 │
│  Następny plan używa nowych współczynników      │
└──────────────────────────────────────────────────┘
```

## 🎯 Parametry dostępne w HA

### Współczynniki PV
- `input_number.pv_planner_pv_before_13_ratio` (30–70%, domyślnie 60%)
- `input_number.pv_planner_pv_after_13_ratio` (30–70%, domyślnie 40%)

### Offsety słońca
- `input_number.pv_planner_pv_dawn_offset_min` (0–120 min, domyślnie 45)
- `input_number.pv_planner_pv_dusk_offset_min` (0–120 min, domyślnie 30)

### Limity programów
- `input_number.pv_planner_program_3_earliest_hour` (0–23, domyślnie 6)
- `input_number.pv_planner_program_3_earliest_min` (0–59, domyślnie 5)
- `input_number.pv_planner_program_6_earliest_hour` (0–23, domyślnie 15)
- `input_number.pv_planner_program_6_earliest_min` (0–59, domyślnie 5)

### Profile zużycia
- `input_number.pv_planner_house_load_night` (0–5 kW, domyślnie 0.4)
- `input_number.pv_planner_house_load_morning_day` (0–5 kW, domyślnie 0.6)
- `input_number.pv_planner_house_load_evening` (0–5 kW, domyślnie 1.6)
- `input_number.pv_planner_house_load_night_late` (0–5 kW, domyślnie 1.0)

### Taryfy
- `input_select.pv_planner_cheap_tariff_windows` (Noc+Midday / Noc+Popołudnie / Noc)

## 🔍 Troubleshooting

### Encje się nie pojawiają
1. Sprawdź logi HA: `Settings → System → Logs`
2. Przeładuj encje: `Developer Tools → YAML → Reload Helpers`
3. Restart HA

### Zmiany nie są synchronizowane
1. Sprawdź logi AppDaemon: czy jest `PV PLANNER ▶ Synchronizacja...`?
2. Edytuj suwak w HA - powinna być zmiana stanu
3. Sprawdzić kod `ha_sync.py` — czy są importy?

### Błędy przy imporcie ha_sync
- Upewnij się, że plik `ha_sync.py` jest w katalogu `apps/pv_planner/`
- Sprawdź, czy `__init__.py` istnieje w katalogu

## 📝 Notatki

- Parametry są aktualizowane **w realtime** bez restartu AppDaemon
- Zmienne w `config.py` i `planner_core.py` są synchronizowane
- Wartości są przechowywane w HA i persystentne po restarcie
