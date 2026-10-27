"""MCP23017 I²C port expander driver."""
import logging

logger = logging.getLogger('halung.hardware.mcp23017')


class MCP23017:
    """MCP23017 16-bit I/O expander."""

    def __init__(self, i2c_address=0x20, i2c_bus=1):
        self.address = i2c_address
        self.bus = i2c_bus
        self.logger = logging.getLogger(f'MCP23017_0x{i2c_address:02x}')
        self.logger.info(f"Initialized at address 0x{i2c_address:02x} on bus {i2c_bus}")

    def write_register(self, register, value):
        """Write to MCP register."""
        self.logger.debug(f"Write reg 0x{register:02x} = 0x{value:02x}")
        # TODO: Implement actual I²C write

    def read_register(self, register):
        """Read from MCP register."""
        # TODO: Implement actual I²C read
        return 0xFF

    def set_port_direction(self, port_a_direction, port_b_direction):
        """Set GPIO direction (0=output, 1=input)."""
        self.write_register(0x00, port_a_direction)  # IODIRA
        self.write_register(0x01, port_b_direction)  # IODIRB
        self.logger.info(f"Port A: 0x{port_a_direction:02x}, Port B: 0x{port_b_direction:02x}")
