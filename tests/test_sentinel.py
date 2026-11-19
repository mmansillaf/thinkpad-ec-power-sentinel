"""Unit tests for ThinkPad EC & Power Sentinel (standard unittest)."""

import unittest
from pathlib import Path
from unittest.mock import patch

from src.sentinel import (
    ACPIParameters,
    PowerSupplyInfo,
    SystemReport,
    ThinkPadSentinel,
    TypeCPortInfo,
)


class TestThinkPadSentinel(unittest.TestCase):
    """Test suite for sentinel telemetry and recommendations."""

    def test_power_supply_info_dataclass(self):
        """Verify PowerSupplyInfo fields and values."""
        psi = PowerSupplyInfo(
            name="BAT0",
            supply_type="Battery",
            status="Charging",
            online=None,
            capacity=85,
            voltage_now=12000000,
            charge_control_start=0,
            charge_control_end=100,
        )
        self.assertEqual(psi.name, "BAT0")
        self.assertEqual(psi.status, "Charging")
        self.assertEqual(psi.capacity, 85)

    def test_typec_port_info_dataclass(self):
        """Verify TypeCPortInfo initialization."""
        port = TypeCPortInfo(
            name="port0",
            data_role="host [device]",
            power_role="source [sink]",
            power_operation_mode="usb_power_delivery",
            pd_revision="2.0",
        )
        self.assertEqual(port.name, "port0")
        self.assertEqual(port.power_operation_mode, "usb_power_delivery")

    def test_read_file_safe(self):
        """Test safe reading of non-existent paths."""
        missing = Path("/path/that/does/not/exist_test_sentinel")
        self.assertEqual(ThinkPadSentinel._read_file(missing), "N/A")

    @patch.object(ThinkPadSentinel, "get_hardware_info", return_value=("ThinkPad P53", "1.30", "6.8.0"))
    @patch.object(
        ThinkPadSentinel,
        "inspect_power_supplies",
        return_value=[
            PowerSupplyInfo("AC", "Mains", "N/A", online=0, capacity=None, voltage_now=None, charge_control_start=None, charge_control_end=None),
            PowerSupplyInfo("BAT0", "Battery", "Discharging", online=None, capacity=18, voltage_now=11800000, charge_control_start=0, charge_control_end=100),
        ],
    )
    @patch.object(
        ThinkPadSentinel,
        "inspect_typec",
        return_value=[
            TypeCPortInfo("port0", "device", "sink", "default", "2.0")
        ],
    )
    @patch.object(
        ThinkPadSentinel,
        "inspect_acpi",
        return_value=ACPIParameters(ec_event_clearing="query", ec_busy_polling="N", ec_storm_threshold="8"),
    )
    @patch.object(ThinkPadSentinel, "check_dmesg_ec_storm", return_value=True)
    def test_generate_report_recommendations(self, mock_dmesg, mock_acpi, mock_typec, mock_ps, mock_hw):
        """Test recommendation generation when AC is offline and storm detected."""
        report = ThinkPadSentinel.generate_report()
        self.assertEqual(report.model_name, "ThinkPad P53")
        self.assertTrue(report.ec_storm_detected)
        self.assertGreaterEqual(len(report.recommendations), 2)
        self.assertTrue(any("acpi_ec_event_processor" in r for r in report.recommendations))


if __name__ == "__main__":
    unittest.main()
