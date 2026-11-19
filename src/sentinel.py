#!/usr/bin/env python3
"""ThinkPad EC & Power Sentinel.

Non-destructive diagnostic and telemetry utility for ThinkPad ACPI,
Embedded Controller (EC), USB Power Delivery, and power supply subsystems on Linux.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PowerSupplyInfo:
    """Telemetry information for a single power supply device."""

    name: str
    supply_type: str
    status: str
    online: Optional[int]
    capacity: Optional[int]
    voltage_now: Optional[int]
    charge_control_start: Optional[int]
    charge_control_end: Optional[int]


@dataclass
class TypeCPortInfo:
    """Telemetry for USB-C and Power Delivery ports."""

    name: str
    data_role: str
    power_role: str
    power_operation_mode: str
    pd_revision: str


@dataclass
class ACPIParameters:
    """ACPI module parameter configuration."""

    ec_event_clearing: str
    ec_busy_polling: str
    ec_storm_threshold: str


@dataclass
class SystemReport:
    """Consolidated system telemetry report."""

    model_name: str
    bios_version: str
    kernel_version: str
    power_supplies: List[PowerSupplyInfo] = field(default_factory=list)
    typec_ports: List[TypeCPortInfo] = field(default_factory=list)
    acpi_params: Optional[ACPIParameters] = None
    ec_storm_detected: bool = False
    recommendations: List[str] = field(default_factory=list)


class ThinkPadSentinel:
    """Inspector for ThinkPad power subsystems."""

    SYSFS_POWER = Path("/sys/class/power_supply")
    SYSFS_TYPEC = Path("/sys/class/typec")
    SYSFS_ACPI_PARAMS = Path("/sys/module/acpi/parameters")
    DMI_PATH = Path("/sys/devices/virtual/dmi/id")

    @staticmethod
    def _read_file(path: Path) -> str:
        """Safely read string from a sysfs or procfs node."""
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return "N/A"

    @classmethod
    def get_hardware_info(cls) -> tuple[str, str, str]:
        """Read system hardware and BIOS data from DMI."""
        model = cls._read_file(cls.DMI_PATH / "product_name")
        version = cls._read_file(cls.DMI_PATH / "bios_version")
        kernel = cls._read_file(Path("/proc/sys/kernel/osrelease"))
        return model, version, kernel

    @classmethod
    def inspect_power_supplies(cls) -> List[PowerSupplyInfo]:
        """Query all registered power supplies in sysfs."""
        supplies: List[PowerSupplyInfo] = []
        if not cls.SYSFS_POWER.exists():
            return supplies

        for entry in sorted(cls.SYSFS_POWER.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            stype = cls._read_file(entry / "type")
            status = cls._read_file(entry / "status")

            online_raw = cls._read_file(entry / "online")
            online = int(online_raw) if online_raw.isdigit() else None

            cap_raw = cls._read_file(entry / "capacity")
            cap = int(cap_raw) if cap_raw.isdigit() else None

            v_raw = cls._read_file(entry / "voltage_now")
            voltage = int(v_raw) if v_raw.isdigit() else None

            start_raw = cls._read_file(entry / "charge_control_start_threshold")
            c_start = int(start_raw) if start_raw.isdigit() else None

            end_raw = cls._read_file(entry / "charge_control_end_threshold")
            c_end = int(end_raw) if end_raw.isdigit() else None

            supplies.append(
                PowerSupplyInfo(
                    name=name,
                    supply_type=stype,
                    status=status,
                    online=online,
                    capacity=cap,
                    voltage_now=voltage,
                    charge_control_start=c_start,
                    charge_control_end=c_end,
                )
            )
        return supplies

    @classmethod
    def inspect_typec(cls) -> List[TypeCPortInfo]:
        """Query USB-C port roles and power delivery negotiation."""
        ports: List[TypeCPortInfo] = []
        if not cls.SYSFS_TYPEC.exists():
            return ports

        for entry in sorted(cls.SYSFS_TYPEC.glob("port*")):
            if not entry.is_dir():
                continue
            name = entry.name
            data_role = cls._read_file(entry / "data_role")
            power_role = cls._read_file(entry / "power_role")
            op_mode = cls._read_file(entry / "power_operation_mode")
            rev = cls._read_file(entry / "usb_power_delivery_revision")
            ports.append(
                TypeCPortInfo(
                    name=name,
                    data_role=data_role,
                    power_role=power_role,
                    power_operation_mode=op_mode,
                    pd_revision=rev,
                )
            )
        return ports

    @classmethod
    def inspect_acpi(cls) -> Optional[ACPIParameters]:
        """Read current ACPI kernel parameters."""
        if not cls.SYSFS_ACPI_PARAMS.exists():
            return None
        return ACPIParameters(
            ec_event_clearing=cls._read_file(cls.SYSFS_ACPI_PARAMS / "ec_event_clearing"),
            ec_busy_polling=cls._read_file(cls.SYSFS_ACPI_PARAMS / "ec_busy_polling"),
            ec_storm_threshold=cls._read_file(cls.SYSFS_ACPI_PARAMS / "ec_storm_threshold"),
        )

    @classmethod
    def check_dmesg_ec_storm(cls) -> bool:
        """Scan system logs for ACPI EC event queue starvation."""
        try:
            res = subprocess.run(
                ["journalctl", "-k", "-b", "--no-pager"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return "acpi_ec_event_processor hogged CPU" in res.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    @classmethod
    def generate_report(cls) -> SystemReport:
        """Build full telemetry and remediation recommendations."""
        model, bios, kernel = cls.get_hardware_info()
        supplies = cls.inspect_power_supplies()
        ports = cls.inspect_typec()
        acpi_p = cls.inspect_acpi()
        storm = cls.check_dmesg_ec_storm()

        recommendations: List[str] = []

        # Analyze AC vs Battery status
        ac_online = any(s.online == 1 for s in supplies if s.supply_type == "Mains")
        bat_discharging = any(s.status == "Discharging" for s in supplies if s.supply_type == "Battery")

        if not ac_online and bat_discharging:
            recommendations.append(
                "Línea AC offline. Si el cargador está conectado físicamente, existe desincronización de EC o falla de handshake PD."
            )

        if storm:
            recommendations.append(
                "Detectada saturación de cola en acpi_ec_event_processor. Ajustar ec_event_clearing='event' y ec_busy_polling='Y'."
            )

        if any(p.power_operation_mode == "default" for p in ports):
            recommendations.append(
                "Puertos USB-C en modo 'default' (5V pasivo). Desconectar e insertar en puerto Thunderbolt alterno para renegociar 20V."
            )

        return SystemReport(
            model_name=model,
            bios_version=bios,
            kernel_version=kernel,
            power_supplies=supplies,
            typec_ports=ports,
            acpi_params=acpi_p,
            ec_storm_detected=storm,
            recommendations=recommendations,
        )


def main() -> int:
    """CLI entry point for ThinkPad Sentinel."""
    parser = argparse.ArgumentParser(
        description="ThinkPad EC & Power Sentinel - Diagnostic & Telemetry Utility"
    )
    parser.add_argument("--json", action="store_true", help="Output telemetry in JSON format")
    args = parser.parse_args()

    report = ThinkPadSentinel.generate_report()

    if args.json:
        print(json.dumps(asdict(report), indent=2))
        return 0

    print("================================================================")
    print(" ThinkPad EC & Power Sentinel - Reporte de Telemetría")
    print("================================================================")
    print(f"Dispositivo : {report.model_name}")
    print(f"BIOS / EC   : {report.bios_version}")
    print(f"Kernel      : {report.kernel_version}")
    print(f"EC Storm    : {'[ALERTA] Detectada en logs' if report.ec_storm_detected else '[OK] No detectada'}")

    print("\n[Fuentes de Energía / Power Supply]")
    for ps in report.power_supplies:
        on_str = f"Online={ps.online}" if ps.online is not None else ""
        cap_str = f"Cap={ps.capacity}%" if ps.capacity is not None else ""
        print(f"  • {ps.name} ({ps.supply_type}): Status={ps.status} {on_str} {cap_str}")

    print("\n[Puertos Type-C & Power Delivery]")
    for tc in report.typec_ports:
        print(f"  • {tc.name}: PowerRole={tc.power_role} | Modo={tc.power_operation_mode}")

    if report.acpi_params:
        print("\n[Parámetros ACPI del Kernel]")
        print(f"  • ec_event_clearing  : {report.acpi_params.ec_event_clearing}")
        print(f"  • ec_busy_polling    : {report.acpi_params.ec_busy_polling}")
        print(f"  • ec_storm_threshold : {report.acpi_params.ec_storm_threshold}")

    if report.recommendations:
        print("\n[Recomendaciones de Remediación]")
        for rec in report.recommendations:
            print(f"  [!] {rec}")

    print("================================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
