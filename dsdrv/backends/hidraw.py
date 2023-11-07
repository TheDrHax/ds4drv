import fcntl
import itertools
import os

from io import FileIO
from time import sleep

from evdev import InputDevice
from pyudev import Context, Monitor

from ..backend import Backend
from ..exceptions import DeviceError
from ..device import DSDevice
from ..utils import zero_copy_slice
from ..controllers import controllers, determineGenerationHidraw


IOC_RW = 3221243904
def HIDIOCSFEATURE(size): return IOC_RW | (0x06 << 0) | (size << 16)
def HIDIOCGFEATURE(size): return IOC_RW | (0x07 << 0) | (size << 16)

class HidrawDSDevice(DSDevice):
    report_size = 0
    valid_report_id = 0

    def __init__(self, name, addr, type, hidraw_device, event_device):
        try:
            self.report_fd = os.open(hidraw_device, os.O_RDWR | os.O_NONBLOCK)
            self.fd = FileIO(self.report_fd, "rb+", closefd=False)
            self.input_device = InputDevice(event_device)
            self.input_device.grab()
        except (OSError, IOError) as err:
            raise DeviceError(err)

        self.buf = bytearray(self.report_size)
        self.controller = determineGenerationHidraw(self.input_device)

        super(HidrawDSDevice, self).__init__(
            name, addr, type, self.controller)

    def read_report(self):
        try:
            ret = self.fd.readinto(self.buf)
        except IOError:
            return

        # Disconnection
        if ret == 0:
            return

        # Invalid report size or id, just ignore it
        if ret < self.report_size or self.buf[0] != self.valid_report_id:
            return False

        if self.type == "bluetooth":
            # Cut off bluetooth data
            if (self.controller.value.bluetoothOffset_in > 0):
                buf = zero_copy_slice(self.buf, self.controller.value.bluetoothOffset_in)
            else:
                buf = self.buf
        else:
            # Or USB data, depending on the offset
            if (self.controller.value.bluetoothOffset_in < 0):
                buf = zero_copy_slice(self.buf, abs(self.controller.value.bluetoothOffset_in))
            else:
                buf = self.buf

        return self.parse_report(buf)

    def read_feature_report(self, report_id, size):
        op = HIDIOCGFEATURE(size + 1)
        buf = bytearray(size + 1)
        buf[0] = report_id

        return fcntl.ioctl(self.fd, op, bytes(buf))

    def write_report(self, report_id, data):
        hid = bytearray((report_id,))
        self.fd.write(hid + data)

    def close(self):
        try:
            # Reset LED to original hidraw pairing colour.
            self.set_led(0, 0, 1)

            self.fd.close()
            self.input_device.ungrab()
        except IOError:
            pass


class HidrawBluetoothDSDevice(HidrawDSDevice):
    __type__ = "bluetooth"

    @property
    def valid_report_id(self):
        if (self.controller == controllers.DualSense):
            return 0x31
        if (self.controller == controllers.DualShock4):
            return 0x11
        return -1

    report_size = 78

    def set_operational(self):
        self.read_feature_report(self.controller.value.set_operational_op, 37)

class HidrawUSBDSDevice(HidrawDSDevice):
    __type__ = "usb"

    report_size = 64
    valid_report_id = 0x01

    def set_operational(self):
        # Get the bluetooth MAC
        addr = self.read_feature_report(self.controller.value.get_bt_mac_op, 6)[1:]
        addr = ["{0:02x}".format(c) for c in bytearray(addr)]
        addr = ":".join(reversed(addr)).upper()

        self.device_name = "{0} {1}".format(addr, self.device_name)
        self.device_addr = addr


HID_DEVICES = {
    "Sony Interactive Entertainment Wireless Controller": HidrawUSBDSDevice,
    "Sony Interactive Entertainment DualSense Wireless Controller": HidrawUSBDSDevice,
    "Sony Computer Entertainment Wireless Controller": HidrawUSBDSDevice,
    "Wireless Controller": HidrawBluetoothDSDevice,
    "DualSense Wireless Controller": HidrawBluetoothDSDevice,
}


class HidrawBackend(Backend):
    __name__ = "hidraw"

    def setup(self):
        pass

    def _get_future_devices(self, context):
        """Return a generator yielding new devices."""
        monitor = Monitor.from_netlink(context)
        monitor.filter_by("hidraw")
        monitor.start()

        self._scanning_log_message()
        for device in iter(monitor.poll, None):
            if device.action == "add":
                # Sometimes udev rules has not been applied at this point,
                # causing permission denied error if we are running in user
                # mode. With this sleep this will hopefully not happen.
                sleep(1)

                yield device
                self._scanning_log_message()

    def _scanning_log_message(self):
        self.logger.info("Scanning for devices")

    @property
    def devices(self):
        """Wait for new DS4 devices to appear."""
        context = Context()

        existing_devices = context.list_devices(subsystem="hidraw")
        future_devices = self._get_future_devices(context)

        for hidraw_device in itertools.chain(existing_devices, future_devices):
            hid_device = hidraw_device.parent
            if hid_device.subsystem != "hid":
                continue

            cls = HID_DEVICES.get(hid_device.get("HID_NAME"))
            if not cls:
                continue

            for child in hid_device.parent.children:
                event_device = child.get("DEVNAME", "")

                if event_device.startswith("/dev/input/event"):
                    break
            else:
                continue

            try:
                device_addr = hid_device.get("HID_UNIQ", "").upper()
                if device_addr:
                    device_name = "{0} {1}".format(device_addr,
                                                   hidraw_device.sys_name)
                else:
                    device_name = hidraw_device.sys_name

                yield cls(name=device_name,
                          addr=device_addr,
                          type=cls.__type__,
                          hidraw_device=hidraw_device.device_node,
                          event_device=event_device)

            except DeviceError as err:
                self.logger.error("Unable to open DS device: {0}", err)
