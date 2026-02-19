# MD3 Dashboard Customizations

**Based on:** v5.0.0 (2025-02-11)  
**Last updated:** [date you pulled]

## Entity ID mappings

| Upstream | Mine |
|-------------------|----------|
| `sensor.weather_temperature` | `sensor.outdoor_temperature` |
| `climate.living_room` | `climate.thermostat_main` |
| `light.living_room_ceiling` | `light.living_room_main` |
| ... | ... |

## Room names

| Upstream | Mine |
|----------|------|
| Living Room | Great Room |
| Master Bedroom | Bedroom |
| ... | ... |

## Streamline templates

- **File:** `assets/streamline_templates/...`
- **Changes:** Room list, entity references for each room
- **My rooms:** [list]

## Features disabled/removed/swapped

- Alarmo
- Swap Hue for Lifx
- Swap sprinklers for Rachio

## Features added

- [Any cards or sections you added]

## Files I typically modify

- `dashboard.yaml` – entity IDs, room references
- `assets/streamline_templates/*` – room config
- `template sensor/` – if using their sensors, adapt to mine
