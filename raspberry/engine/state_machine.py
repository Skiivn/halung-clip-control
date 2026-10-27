"""Clip Test state machine — Core cycle logic."""
import logging
import json
from datetime import datetime
from enum import Enum

logger = logging.getLogger('halung.engine.state_machine')


class CycleState(Enum):
    """Clip test cycle states."""
    READY = "READY"
    SWLOCK = "SWLOCK"
    CHECKING = "CHECKING"
    WRONG_CLIP = "WRONG_CLIP"
    VALIDATED = "VALIDATED"
    WAIT_RELEASE = "WAIT_RELEASE"
    ERROR = "ERROR"


class StateMachine:
    """Clip test state machine."""

    def __init__(self, program_config):
        self.program = program_config
        self.state = CycleState.READY
        self.cycle_start = None
        self.swlock_time = None
        self.butok_time = None
        self.logger = logging.getLogger('ClipTestEngine')
        self.logger.info(f"StateMachine initialized for program: {program_config.get('name', 'UNKNOWN')}")

    def on_swlock_pressed(self):
        """Handle SWLOCK button press."""
        if self.state == CycleState.READY:
            self.state = CycleState.SWLOCK
            self.swlock_time = datetime.now().isoformat()
            self.logger.info("→ SWLOCK detected")
            return True
        return False

    def check_all_switches(self, pressed_channels):
        """Verify all required points match program."""
        required = set(self.program.get('required_switches', []))
        actual = set(pressed_channels)
        
        if actual == required:
            self.state = CycleState.CHECKING
            self.logger.info(f"✓ All {len(required)} points verified")
            return True
        else:
            missing = required - actual
            extra = actual - required
            self.logger.warning(f"✗ Mismatch: missing {missing}, extra {extra}")
            return False

    def on_butok_pressed(self):
        """Handle BUTOK button press."""
        if self.state == CycleState.CHECKING:
            self.butok_time = datetime.now().isoformat()
            self.state = CycleState.VALIDATED
            self.logger.info("→ BUTOK pressed, cycle validated")
            return True
        return False

    def on_all_released(self):
        """Handle all points released."""
        if self.state == CycleState.VALIDATED:
            self.state = CycleState.READY
            self.logger.info("→ All points released, cycle complete")
            return self.get_cycle_report()
        return None

    def get_cycle_report(self):
        """Generate cycle report."""
        if self.swlock_time and self.butok_time:
            start = datetime.fromisoformat(self.swlock_time)
            end = datetime.fromisoformat(self.butok_time)
            cycle_seconds = (end - start).total_seconds()
            
            target_per_hour = self.program.get('target_per_hour', 45)
            actual_per_hour = 3600.0 / cycle_seconds if cycle_seconds > 0 else 0
            efficiency = (actual_per_hour / target_per_hour * 100) if target_per_hour > 0 else 0
            
            return {
                'status': 'OK',
                'cycle_time_seconds': cycle_seconds,
                'swlock_time': self.swlock_time,
                'butok_time': self.butok_time,
                'actual_per_hour': round(actual_per_hour, 1),
                'efficiency': round(efficiency, 1),
                'variant_ref': self.program.get('variant_ref', ''),
                'operator': self.program.get('operator', '')
            }
        return None
