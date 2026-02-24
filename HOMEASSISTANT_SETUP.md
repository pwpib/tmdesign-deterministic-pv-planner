# PV Planner - Parametry w Home Assistant

## 📋 Przegląd

Ten dokument opisuje, jak wystawić parametry konfiguracyjne PV Planner'a w interfejsie Home Assistant.

## 🚀 Instalacja

### Krok 1: Dodaj plik konfiguracji HA

W Home Assistant, dodaj zawartość `homeassistant_config.yaml` do `configuration.yaml`:

```yaml
# configuration.yaml

# Importuj konfigurację PV Planner'a
input_number: !include apps/pv_planner/input_numbers.yaml
input_select: !include apps/pv_planner/input_select.yaml
template: !include apps/pv_planner/template.yaml
automation: !include_dir_merge_list apps/pv_planner/automations/
```

Lub skopiuj zawartość bezpośrednio do `configuration.yaml`.

### Krok 2: Restart Home Assistant

```bash
# W terminalu HA lub przez UI
dev-tools → YAML → Restart Home Assistant
```

### Krok 3: Zweryfikuj encje

Przejdź do **Settings → Devices & Services → Helpers** i poszukaj:
- `pv_planner_*` (input_number)
- `pv_planner_cheap_tariff_windows` (input_select)

---

## 📊 Parametry w HA

### Współczynniki PV

| Encja | Typ | Min | Max | Domyślnie | Opis |
|-------|-----|-----|-----|----------|------|
| `pv_planner_pv_before_13_ratio` | slider | 30% | 70% | **60%** | Udział energii PV przed 13:00 |
| `pv_planner_pv_after_13_ratio` | slider | 30% | 70% | **40%** | Udział energii PV po 13:00 |

### Offsety czasowe słońca

| Encja | Typ | Min | Max | Domyślnie | Opis |
|-------|-----|-----|-----|----------|------|
| `pv_planner_pv_dawn_offset_min` | slider | 0 | 120 min | **45 min** | Start produkcji PV (po wschodzie) |
| `pv_planner_pv_dusk_offset_min` | slider | 0 | 120 min | **30 min** | Koniec produkcji PV (przed zachodem) |

### Limity czasowe programów

| Encja | Typ | Min | Max | Domyślnie | Opis |
|-------|-----|-----|-----|----------|------|
| `pv_planner_program_3_earliest_hour` | slider | 0 | 23 | **6** | Godzina - Program 3 |
| `pv_planner_program_3_earliest_min` | slider | 0 | 59 | **5** | Minuta - Program 3 |
| `pv_planner_program_6_earliest_hour` | slider | 0 | 23 | **15** | Godzina - Program 6 |
| `pv_planner_program_6_earliest_min` | slider | 0 | 59 | **5** | Minuta - Program 6 |

### Profile zużycia domu

| Encja | Typ | Min | Max | Domyślnie | Opis |
|-------|-----|-----|-----|----------|------|
| `pv_planner_house_load_night` | slider | 0.0 | 5.0 | **0.4 kW** | Zużycie (0–6h) |
| `pv_planner_house_load_morning_day` | slider | 0.0 | 5.0 | **0.6 kW** | Zużycie (6–15h) |
| `pv_planner_house_load_evening` | slider | 0.0 | 5.0 | **1.6 kW** | Zużycie (15–20h) |
| `pv_planner_house_load_night_late` | slider | 0.0 | 5.0 | **1.0 kW** | Zużycie (20–24h) |

### Taryfy prądowe

| Encja | Typ | Opcje | Domyślnie | Opis |
|-------|-----|-------|----------|------|
| `pv_planner_cheap_tariff_windows` | select | Noc+Midday, Noc+Popołudnie, Noc | **Noc+Midday** | Okresy taniej taryfy |

---

## 🔄 Synchronizacja z AppDaemon

Plik `homeassistant_config.yaml` zawiera automation, która:

1. **Monitoruje zmiany** parametrów w HA
2. **Ustawia flagę** `input_boolean.pv_planner_config_updated`
3. AppDaemon może czytać tę flagę i wczytać nowe wartości

### Integracja z AppDaemon:

Dodaj do `pv_planner_app.py`:

```python
def _on_config_update(self, entity, attribute, old, new, kwargs):
    """Odpowiedź na zmianę konfiguracji w HA"""
    self.log("PV PLANNER ▶ Konfiguracja zmieniona w HA")
    
    # Wczytaj nowe wartości z HA
    pv_before_13 = float(self.get_state("input_number.pv_planner_pv_before_13_ratio")) / 100.0
    pv_after_13 = float(self.get_state("input_number.pv_planner_pv_after_13_ratio")) / 100.0
    
    # Zaktualizuj globalne zmienne
    import pv_planner.config as config
    config.PV_BEFORE_13_RATIO = pv_before_13
    config.PV_AFTER_13_RATIO = pv_after_13
    
    self.log(f"PV_BEFORE_13_RATIO: {pv_before_13}")
    self.log(f"PV_AFTER_13_RATIO: {pv_after_13}")

# W initialize():
self.listen_state(
    self._on_config_update,
    "input_boolean.pv_planner_config_updated",
    new="on"
)
```

---

## 🎛️ Widok w Home Assistant

Po instalacji będziesz mieć widok:

```
Settings → Devices & Services → Helpers

📊 PV Planner - Współczynniki
  ├─ 🔹 Udział energii PV przed 13:00: 60%
  ├─ 🔹 Udział energii PV po 13:00: 40%

⏰ PV Planner - Offsety czasowe
  ├─ 🔹 Offset wschodu słońca: 45 min
  ├─ 🔹 Offset zachodu słońca: 30 min

🕒 PV Planner - Limity programów
  ├─ 🔹 Program 3 - najwcześniej: 06:05
  ├─ 🔹 Program 6 - najwcześniej: 15:05

⚡ PV Planner - Zużycie domu
  ├─ 🔹 Noc (0–6h): 0.4 kW
  ├─ 🔹 Dzień (6–15h): 0.6 kW
  ├─ 🔹 Wieczór (15–20h): 1.6 kW
  ├─ 🔹 Późna noc (20–24h): 1.0 kW

💰 PV Planner - Taryfy
  └─ 🔹 Okna tanich taryf: Noc (22-6h) + Midday (13-15h)
```

---

## 🧪 Test

1. Zmień wartość suwaka w HA (np. `pv_planner_pv_before_13_ratio` na 65%)
2. Sprawdź logi AppDaemon
3. Powinieneś zobaczyć: `PV PLANNER ▶ Konfiguracja zmieniona w HA`

---

## 📝 Notatki

- Wszystkie wartości są **domyślne** i odpowiadają wartościom z `config.py`
- Zmienia wartości w HA **nie wpłyną** na kod, dopóki AppDaemon nie wczyta aktualizacji
- Automation zapewnia **persistencję** - wartości będą zapamiętane po restarcie

---

## 🔗 Linkowanie z Config

Aby zmiana w HA automatycznie aktualizowała `config.py`, potrzebujesz dodać kod w AppDaemon,
który będzie czytać `input_number` encje i aktualizować swoje stałe w runtime'ie.

Zaraz przygotuje kod do integracji AppDaemon z HA! 🚀
