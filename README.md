# ThinkPad EC & Power Delivery Sentinel

Herramienta de telemetría, auditoría forense y recuperación en caliente para subsistemas de energía (Embedded Controller, ACPI, USB-PD y drivers de batería) en portátiles Lenovo ThinkPad (series P, T, X) sobre Linux.

## Arquitectura de Diagnóstico y Mitigación

```mermaid
flowchart TD
    A["Inserción del Adaptador AC"] --> B["Lectura de Pin de Sensado / EC Beep"]
    B --> C{"Estado de Cola ACPI en Kernel"}
    C -- "Saturación acpi_ec_event_processor" --> D["Bloqueo de Negociación: AC online=0"]
    C -- "Cola Normal" --> E["Handshake PD 20V / Slim-Tip Activo"]
    D --> F["thinkpad_ec_recover.sh (Recarga Módulos + Ajuste ACPI)"]
    F --> G["ec_event_clearing = event | ec_busy_polling = Y"]
    G --> H{"¿Conmuta a online=1?"}
    H -- "Sí" --> I["Batería Charging"]
    H -- "No" --> J["Pinhole Cold Reset (30s en Base Inferior)"]
    J --> I
    E --> I
```

```text
┌───────────────────────────────────────────────────────────────┐
│                 Inserción del Adaptador AC                    │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│            Lectura de Pin de Sensado / EC Beep                │
└───────────────────────────────┬───────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────┐
│             Estado de Cola ACPI en Kernel                     │
└───────────────┬───────────────────────────────┬───────────────┘
                │                               │ Normal
                ▼ Saturada                      ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│  Bloqueo: AC online = 0      │ │  Handshake PD 20V / Slim-Tip │
└───────────────┬──────────────┘ └──────────────┬───────────────┘
                │                               │
                ▼                               │
┌──────────────────────────────┐                │
│    thinkpad_ec_recover.sh    │                │
│ (Recarga drivers + ACPI tune)│                │
└───────────────┬──────────────┘                │
                │                               │
                ▼                               │
┌──────────────────────────────┐                │
│     ¿Conmuta a online=1?     │                │
└───────┬──────────────┬───────┘                │
        │ Sí           │ No                     │
        │              ▼                        │
        │ ┌──────────────────────────────┐      │
        │ │   Pinhole Cold Reset (30s)   │      │
        │ └────────────┬─────────────────┘      │
        │              │                        │
        ▼              ▼                        ▼
┌───────────────────────────────────────────────────────────────┐
│                      Batería Charging                         │
└───────────────────────────────────────────────────────────────┘
```

## Características Técnicas

- **Telemetría no destructiva**: Inspección directa de nodos `sysfs` (`/sys/class/power_supply/`, `/sys/class/typec/`, `/sys/module/acpi/parameters/`).
- **Detección de tormentas de eventos EC**: Rastreo en logs de kernel de bloqueos en `acpi_ec_event_processor`.
- **Ajuste dinámico ACPI**: Conmutación de `ec_event_clearing` a modo `event` y activación de `ec_busy_polling` para erradicar retrasos de interrupción tras suspensión S3.
- **Normalización de umbrales**: Limpieza de registros corruptos en `charge_control_start_threshold` y `charge_control_end_threshold`.

## Uso Rápido

### 1. Auditoría de Telemetría (Python)

```bash
# Reporte en texto plano
python3 -m src.sentinel

# Salida estructurada en JSON
python3 -m src.sentinel --json
```

### 2. Remediación en Caliente (Bash / Root)

```bash
sudo ./scripts/thinkpad_ec_recover.sh
```

### 3. Pruebas Unitarias

```bash
python3 -m unittest discover -s tests -v
```

## Protocolo de Reseteo Físico por Hardware (Pinhole Reset)

Si el Embedded Controller mantiene energía residual en compuertas tras fallos críticos:

1. Apagar el equipo por completo (`sudo poweroff`) y desconectar el cargador.
2. Insertar un clip en el orificio **Emergency Reset Hole** ubicado en el panel inferior durante **30 segundos continuos**.
3. Mantener presionado el botón de encendido frontal durante **30 segundos** sin fuente conectada (drenaje capacitivo).
4. Reconectar el cargador y encender.

## Licencia

Distribuido bajo licencia MIT. Autor: Moises Mansilla F. (mmansillaf@gmail.com).
