from enum import Enum


class controller:
    """Each instance holds a map between the hid report to the controller's layout
    """

    def __init__(self, valid_report_id, get_bt_mac_op, set_operational_op,
                 bluetoothOffset_in, lstick_start, rstick_start, dpadByte, l2_analog, r2_analog, rl_digital, symbols,
                 trackpadps, accel_start, gyro_start, batt_and_in, touchpad_start,
                 output_report_id, output_report_size, bluetoothOffset_out, led_bit):
        self.valid_report_id = valid_report_id
        self.get_bt_mac_op = get_bt_mac_op
        self.set_operational_op = set_operational_op
        self.bluetoothOffset_in = bluetoothOffset_in
        self.lstick_start = lstick_start
        self.rstick_start = rstick_start
        self.dpadByte = dpadByte
        self.l2_analog = l2_analog
        self.r2_analog = r2_analog
        self.rl_digital = rl_digital
        self.symbols = symbols
        self.trackpadps = trackpadps
        self.accel_start = accel_start
        self.gyro_start = gyro_start
        self.batt_and_in = batt_and_in
        self.touchpad_start = touchpad_start
        self.output_report_id = output_report_id
        self.output_report_size = output_report_size
        self.bluetoothOffset_out = bluetoothOffset_out
        self.led_bit = led_bit


class controllers(Enum):
    """A definition of each controller type

    Some attributes may contain a [usb, bluetooth] list
"""
    DualShock4 = controller([0x01, 0x11], 0x81, 0x02,
                            2, 1, 3, 5, 8, 9, 6, 5, 7, 13, 19, 30, 35, [0xff, 0x80], [31, 77], 2, 5)
    DualSense = controller([0x01, 0x31], 0x09, 0x09,
                           1, 1, 3, 8, 5, 6, 9, 8, 10, 16, 22, 54, 33, [0x02, 0x31], [77, 77], 0, 45)


products = {
    "09cc": controllers.DualShock4,
    "054c": controllers.DualShock4,
    "05c4": controllers.DualShock4,
    "0ce6": controllers.DualSense
}


def determineGenerationHidraw(input_device):
    productCode = "{:04x}".format(input_device.info.product)
    return products.get(productCode)
