#!/usr/bin/env bash
# ==============================================================================
# thinkpad_ec_recover.sh - ThinkPad Embedded Controller & ACPI Power Restorer
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo " [ThinkPad EC Sentinel] Iniciando Diagnóstico y Remediación"
echo "=========================================================="

# 1. Verificación de privilegios de superusuario
if [[ $EUID -ne 0 ]]; then
   echo "[-] Este script debe ejecutarse con privilegios de root (sudo)." >&2
   exit 1
fi

echo "[+] 1. Auditoría inicial de fuentes de energía..."
for ps in /sys/class/power_supply/*; do
  if [[ -d "$ps" ]]; then
    dev=$(basename "$ps")
    type=$(cat "$ps/type" 2>/dev/null || echo "N/A")
    status=$(cat "$ps/status" 2>/dev/null || echo "N/A")
    online=$(cat "$ps/online" 2>/dev/null || echo "N/A")
    cap=$(cat "$ps/capacity" 2>/dev/null || echo "N/A")
    echo "    - $dev ($type): Status=$status | Online=$online | Cap=$cap%"
  fi
done

echo "[+] 2. Reconfiguración de parámetros ACPI en vivo..."
if [[ -f "/sys/module/acpi/parameters/ec_event_clearing" ]]; then
  echo "event" > /sys/module/acpi/parameters/ec_event_clearing
  echo "    - ec_event_clearing configurado a 'event' (anti-storm S3)"
fi

if [[ -f "/sys/module/acpi/parameters/ec_busy_polling" ]]; then
  echo "Y" > /sys/module/acpi/parameters/ec_busy_polling
  echo "    - ec_busy_polling activado ('Y')"
fi

echo "[+] 3. Normalización de umbrales de batería BAT0..."
if [[ -d "/sys/class/power_supply/BAT0" ]]; then
  if [[ -f "/sys/class/power_supply/BAT0/charge_control_start_threshold" ]]; then
    echo 0 > /sys/class/power_supply/BAT0/charge_control_start_threshold || true
  fi
  if [[ -f "/sys/class/power_supply/BAT0/charge_control_end_threshold" ]]; then
    echo 100 > /sys/class/power_supply/BAT0/charge_control_end_threshold || true
  fi
  echo "    - Umbrales restablecidos: Start=0%, Stop=100%"
fi

echo "[+] 4. Recarga en caliente de controladores de bus y Type-C..."
modprobe -r ucsi_acpi typec_ucsi 2>/dev/null || true
modprobe -r thinkpad_acpi 2>/dev/null || true
sleep 1
modprobe thinkpad_acpi
modprobe typec_ucsi
modprobe ucsi_acpi
echo "    - Módulos recargados: thinkpad_acpi, typec_ucsi, ucsi_acpi"

echo "[+] 5. Disparo de eventos udev..."
udevadm trigger --subsystem-match=power_supply
udevadm trigger --subsystem-match=typec
sleep 1

echo "=========================================================="
echo " [ThinkPad EC Sentinel] Estado Posterior a la Remediación"
echo "=========================================================="
ac_online=$(cat /sys/class/power_supply/AC/online 2>/dev/null || echo "N/A")
bat_status=$(cat /sys/class/power_supply/BAT0/status 2>/dev/null || echo "N/A")
echo "    - AC Online: $ac_online"
echo "    - BAT0 Status: $bat_status"

if [[ "$ac_online" == "1" ]]; then
  echo "[✓] Negociación de energía restablecida exitosamente."
else
  echo "[!] AC sigue en 0. Si el cargador está conectado físicamente:"
  echo "    1. Desconecta y reconecta en el puerto Type-C / Slim-Tip alterno."
  echo "    2. Si persiste, apaga el equipo y aplica Pinhole Reset (30s con clip)."
fi
