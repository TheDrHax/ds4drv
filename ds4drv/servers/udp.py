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


class UDPServer:
    def __init__(self, host='', port=26760):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, port))
        self.counter = 0
        self.clients = dict()
        self.remap = False

    def _res_ports(self, index):
        return Message('ports', [
            index,  # pad id
            0x02,  # state (connected)
            0x03,  # model (generic)
            0x01,  # connection type (usb)
            0x00, 0x00, 0x00, 0x00, 0x00, 0xff,  # MAC 00:00:00:00:00:FF
            0xef,  # battery (charged)
            0x00,  # ?
        ])

    @staticmethod
    def _compat_ord(value):
        return ord(value) if sys.version_info < (3, 0) else value

    def _req_ports(self, message, address):
        requests_count = struct.unpack("<i", message[20:24])[0]
        for i in range(requests_count):
            index = self._compat_ord(message[24 + i])

            if (index != 0):  # we have only one controller
                continue

            self.sock.sendto(bytes(self._res_ports(index)), address)

    def _req_data(self, message, address):
        flags = self._compat_ord(message[24])
        reg_id = self._compat_ord(message[25])
        # reg_mac = message[26:32]

        if flags == 0 and reg_id == 0:  # TODO: Check MAC
            if address not in self.clients:
                print('[udp] Client connected: {0[0]}:{0[1]}'.format(address))

            self.clients[address] = time()

    def _res_data(self, message):
        now = time()
        for address, timestamp in self.clients.copy().items():
            if now - timestamp < 5:
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

    def report(self, report):
        if len(self.clients) == 0:
            return None

        data = [
            0x00,  # pad id
            0x02,  # state (connected)
            0x02,  # model (generic)
            0x01,  # connection type (usb)
            0x00, 0x00, 0x00, 0x00, 0x00, 0xff,  # MAC 00:00:00:00:00:FF
            0xef,  # battery (charged)
            0x01  # is active (true)
        ]

        data.extend(bytes(struct.pack('<I', self.counter)))
        self.counter += 1

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

            report.trackpad_touch0_active * 0xFF,
            report.trackpad_touch0_id,

            report.trackpad_touch0_x >> 8,
            report.trackpad_touch0_x & 255,
            report.trackpad_touch0_y >> 8,
            report.trackpad_touch0_y & 255,

            report.trackpad_touch1_active * 0xFF,
            report.trackpad_touch1_id,

            report.trackpad_touch1_x >> 8,
            report.trackpad_touch1_x & 255,
            report.trackpad_touch1_y >> 8,
            report.trackpad_touch1_y & 255,
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

        self._res_data(bytes(Message('data', data)))

    def _worker(self):
        while True:
            self._handle_request(self.sock.recvfrom(1024))

    def start(self):
        self.thread = Thread(target=self._worker)
        self.thread.daemon = True
        self.thread.start()
