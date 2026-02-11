# TMDesign Deterministic PV Battery Planner (D+1)

Deterministyczny planner ładowania magazynu energii dla Home Assistant + AppDaemon.

Projekt planuje dzień D+1 na podstawie:
- prognozy PV
- prognozy temperatury
- modelu pompy ciepła
- parametrów systemowych
- stanu magazynu energii

---

## Dlaczego deterministyczny?

Większość automatyzacji działa reaktywnie:  
„Jeśli X to Y”.

Ten system:
1. Najpierw analizuje cały dzień.
2. Tworzy plan.
3. Realizuje plan konsekwentnie.

Magazyn energii służy do przenoszenia energii w czasie.

Zasada nadrzędna:  
Opróżniamy magazyn tylko wtedy, gdy wiemy, że zostanie napełniony.

Priorytet źródeł:
1. PV  
2. Magazyn  
3. Sieć  

---

## Architektura

Home Assistant  
→ Snapshot danych  
→ Planner Core  
→ Baza planów (SQLite)  
→ Executor  
→ Falownik (target SOC + charging source)

Planner NIE steruje mocą.  
Steruje wyłącznie:
- target SOC (% całkowite)
- charging source (Grid / Disabled)

---

## Struktura projektu

    apps/tmdesign_pv_planner/
        snapshot.py
        planner_core.py
        plan_store.py
        plan_reader.py
        planner_executor.py
        pv_planner_app.py

---

## Wymagane encje Home Assistant

Temperatura:
- sensor.temp_avg_tomorrow

PV:
- sensor.pv_forecast_tomorrow

Magazyn:
- sensor.battery_energy_now_kwh
- input_number.battery_capacity_kwh
- input_number.battery_soc_min_winter
- input_number.battery_soc_min_summer
- input_number.battery_soc_max

Sezon:
- binary_sensor.heating_season_active
- binary_sensor.summer_season_active

---

## Instalacja

1. Zainstaluj AppDaemon.
2. Skopiuj katalog:

       apps/tmdesign_pv_planner/

   do:

       /config/appdaemon/apps/

3. Dodaj do pliku apps.yaml:

       tmdesign_pv_planner:
         module: pv_planner_app
         class: PVPlannerApp

4. Restart AppDaemon.

---

## Roadmap

- Model godzinowy (fundament systemu)
- Walidacja plan vs rzeczywistość
- Optymalizacja okien czasowych
- Dynamiczne taryfy
- Wersja 1.0
