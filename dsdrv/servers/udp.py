from __future__ import division
from builtins import bytes

from threading import Thread
import sys
import socket
import struct
from binascii import crc32
from time import time


class Message(list):
    Types = dict(version=bytes([0x00, 0x00, 0x10, 0x00]),
                 ports=bytes([0x01, 0x00, 0x10, 0x00]),
                 data=bytes([0x02, 0x00, 0x10, 0x00]))

    def __init__(self, message_type, data):
        self.extend([
            0x44, 0x53, 0x55, 0x53,  # DSUS,
            0xE9, 0x03,  # protocol version (1001),
        ])

        # data length
        self.extend(bytes(struct.pack('<H', len(data) + 4)))

        self.extend([
            0x00, 0x00, 0x00, 0x00,  # place for CRC32
            0xff, 0xff, 0xff, 0xff,  # server ID
        ])

        self.extend(Message.Types[message_type])  # data type

        self.extend(data)

        # CRC32
        crc = crc32(bytes(self)) & 0xffffffff
        self[8:12] = bytes(struct.pack('<I', crc))


class Registration:
    def __init__(self, mode=0, slot=None, mac=None):
        self.mode = mode
        self.slot = slot

        self.mac = None

        if mac:
            self.mac = ':'.join(hex(b)[2:].zfill(2) for b in mac).upper()

        self.refresh()

    @property
    def timed_out(self):
        return time() - self.ts > 5

    def refresh(self):
        self.ts = time()

    @property
    def mode_str(self):
        if self.mode == 0:
            return 'all'
        elif self.mode == 1:
            return 'slot={}'.format(self.slot)
        elif self.mode == 2:
            return 'mac={}'.format(self.mac)
        else:
            return 'unknown'

    def match(self, index, controller):
        if self.mode == 0:
            return True

        if self.mode == 1 and index == self.slot:
            return True

        if self.mode == 2 and controller.device.device_addr == self.mac:
            return True

        return False


class UDPServer:
    def __init__(self, host='', port=26760):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.clients = dict()
        self.remap = False
        self.send_touch = True
        self.controllers = {}
        self.counters = {}

    def register_controller(self, controller):
        index = controller.index - 1

        self.controllers[index] = controller
        self.counters[index] = 0

        def handle_report(report):
            self.report(index, controller, report)

        controller.loop.register_event("device-report", handle_report)

    def _slot_info(self, index):
        mac = [0x00, 0x00, 0x00, 0x00, 0x00, 0xff] # 00:00:00:00:00:FF
        conn_type = 0
        state = 0

        controller = None

        if index in self.controllers:
            controller = self.controllers[index]

        if controller and controller.device:
            mac = [int('0x' + i, 16)
                   for i in controller.device.device_addr.split(':')]

            state = 2
            conn_type = 2 if controller.device.type == 'bluetooth' else 1

        return [
            index,  # pad id
            state,
            0x02,  # gyro (full gyro)
            conn_type,  # connection type,
            *mac,  # MAC,
            0xef,  # battery (charged) TODO
        ]

    def _res_ports(self, index):
        return Message('ports', [
            *self._slot_info(index),
            0x00,  # ?
        ])

    @staticmethod
    def _compat_ord(value):
        return ord(value) if sys.version_info < (3, 0) else value

    def _req_ports(self, message, address):
        requests_count = struct.unpack("<i", message[20:24])[0]

        for i in range(requests_count):
            index = self._compat_ord(message[24 + i])

            if (index > len(self.controllers) - 1):
                continue

            self.sock.sendto(bytes(self._res_ports(index)), address)

    def _req_data(self, message, address):
        mode = self._compat_ord(message[20])
        slot = self._compat_ord(message[21])
        mac = message[22:28]

        if address not in self.clients:
            reg = Registration(mode, slot, mac)
            self.clients[address] = reg
            print('[udp] Client connected: {0[0]}:{0[1]} (mode: {1})'.format(address, reg.mode_str))
        else:
            self.clients[address].refresh()

    def _res_data(self, message, index, controller):
        for address, registration in self.clients.copy().items():
            if not registration.timed_out:
                if registration.match(index, controller):
                    self.sock.sendto(message, address)
            else:
                print('[udp] Client disconnected: {0[0]}:{0[1]}'.format(address))
                del self.clients[address]

    def _handle_request(self, request):
        message, address = request

        # client_id = message[12:16]
        msg_type = message[16:20]

        if msg_type == Message.Types['version']:
            return
        elif msg_type == Message.Types['ports']:
            self._req_ports(message, address)
        elif msg_type == Message.Types['data']:
            self._req_data(message, address)
        else:
            print('[udp] Unknown message type: ' + str(msg_type))

    def report(self, index, controller, report):
        if len(self.clients) == 0:
            return None

        # Ignore outdated callbacks
        if index not in self.controllers or self.controllers[index] != controller:
            return None

        data = [
            *self._slot_info(index),
            0x01  # is active (true)
        ]

        data.extend(bytes(struct.pack('<I', self.counters[index])))
        self.counters[index] += 1

        buttons1 = 0x00
        buttons1 |= report.button_share
        buttons1 |= report.button_l3 << 1
        buttons1 |= report.button_r3 << 2
        buttons1 |= report.button_options << 3
        buttons1 |= report.dpad_up << 4
        buttons1 |= report.dpad_right << 5
        buttons1 |= report.dpad_down << 6
        buttons1 |= report.dpad_left << 7

        buttons2 = 0x00
        buttons2 |= report.button_l2
        buttons2 |= report.button_r2 << 1
        buttons2 |= report.button_l1 << 2
        buttons2 |= report.button_r1 << 3
        if not self.remap:
            buttons2 |= report.button_triangle << 4
            buttons2 |= report.button_circle << 5
            buttons2 |= report.button_cross << 6
            buttons2 |= report.button_square << 7
        else:
            buttons2 |= report.button_triangle << 7
            buttons2 |= report.button_circle << 6
            buttons2 |= report.button_cross << 5
            buttons2 |= report.button_square << 4

        data.extend([
            buttons1, buttons2,
            report.button_ps * 0xFF,
            report.button_trackpad * 0xFF,

            report.left_analog_x,
            255 - report.left_analog_y,
            report.right_analog_x,
            255 - report.right_analog_y,

            report.dpad_left * 0xFF,
            report.dpad_down * 0xFF,
            report.dpad_right * 0xFF,
            report.dpad_up * 0xFF,

            report.button_square * 0xFF,
            report.button_cross * 0xFF,
            report.button_circle * 0xFF,
            report.button_triangle * 0xFF,

            report.button_r1 * 0xFF,
            report.button_l1 * 0xFF,

            report.r2_analog,
            report.l2_analog,
        ])

        if self.send_touch:
            data.extend([
                report.trackpad_touch0_active,
                report.trackpad_touch0_id,

                report.trackpad_touch0_x & 255,
                report.trackpad_touch0_x >> 8,
                report.trackpad_touch0_y & 255,
                report.trackpad_touch0_y >> 8,

                report.trackpad_touch1_active,
                report.trackpad_touch1_id,

                report.trackpad_touch1_x & 255,
                report.trackpad_touch1_x >> 8,
                report.trackpad_touch1_y & 255,
                report.trackpad_touch1_y >> 8,
            ])
        else:
            data.extend([
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00
            ])

        data.extend(bytes(struct.pack('<Q', int(time() * 10**6))))

        sensors = [
            report.orientation_roll / 8192,
            - report.orientation_yaw / 8192,
            - report.orientation_pitch / 8192,
            report.motion_y / 16,
            - report.motion_x / 16,
            - report.motion_z / 16,
        ]

        for sensor in sensors:
            data.extend(bytes(struct.pack('<f', float(sensor))))

        self._res_data(bytes(Message('data', data)), index, controller)

    def _worker(self):
        while True:
            self._handle_request(self.sock.recvfrom(1024))

    def start(self):
        self.thread = Thread(target=self._worker)
        self.thread.daemon = True
        self.thread.start()
