from ..action import ReportAction
from ..config import buttoncombo
from ..exceptions import DeviceError
from ..uinput import create_uinput_device
from ..servers import UDPServer

ReportAction.add_option("--emulate-xboxdrv", action="store_true",
                         help="Emulates the same joystick layout as a "
                              "Xbox 360 controller used via xboxdrv")
ReportAction.add_option("--emulate-xpad", action="store_true",
                        help="Emulates the same joystick layout as a wired "
                             "Xbox 360 controller used via the xpad module")
ReportAction.add_option("--emulate-xpad-wireless", action="store_true",
                        help="Emulates the same joystick layout as a wireless "
                             "Xbox 360 controller used via the xpad module")
ReportAction.add_option("--ignored-buttons", metavar="button(s)",
                        type=buttoncombo(","), default=[],
                        help="A comma-separated list of buttons to never send "
                             "as joystick events. For example specify 'PS' to "
                             "disable Steam's big picture mode shortcut when "
                             "using the --emulate-* options")
ReportAction.add_option("--mapping", metavar="mapping",
                        help="Use a custom button mapping specified in the "
                             "config file")
ReportAction.add_option("--trackpad-mouse", action="store_true",
                        help="Makes the trackpad control the mouse")
ReportAction.add_option("--udp", action="store_true",
                        help="Listen for connections from Cemuhook via UDP")
ReportAction.add_option("--udp-host", metavar="IP", default="127.0.0.1",
                        help="Interface that will accept UDP connections")
ReportAction.add_option("--udp-no-touch", action="store_true",
                        help="Do not send touchpad touches to UDP clients")
ReportAction.add_option("--udp-port", metavar="PORT", type=int, default=26760,
                        help="Port that will be listened by the UDP server")
ReportAction.add_option("--udp-remap-buttons", action="store_true",
                        help="Swap A-B and X-Y in UDP reports")


class ReportActionInput(ReportAction):
    """Creates virtual input devices via uinput."""

    def __init__(self, *args, **kwargs):
        super(ReportActionInput, self).__init__(*args, **kwargs)

        self.joystick = None
        self.joystick_layout = None
        self.mouse = None
        self.server = None

        # USB has a report frequency of 4 ms while BT is 2 ms, so we
        # use 5 ms between each mouse emit to keep it consistent and to
        # allow for at least one fresh report to be received inbetween
        self.timer = self.create_timer(0.005, self.emit_mouse)

    def setup(self, device):
        self.timer.start()

    def disable(self):
        self.timer.stop()

        if self.joystick:
            self.joystick.emit_reset()

        if self.mouse:
            self.mouse.emit_reset()

    def load_options(self, options):
        try:
            if options.mapping:
                joystick_layout = options.mapping
            elif options.emulate_xboxdrv:
                joystick_layout = "xboxdrv"
            elif options.emulate_xpad:
                joystick_layout = "xpad"
            elif options.emulate_xpad_wireless:
                joystick_layout = "xpad_wireless"
            else:
                joystick_layout = "ds4"

            if not self.mouse and options.trackpad_mouse:
                self.mouse = create_uinput_device("mouse")
            elif self.mouse and not options.trackpad_mouse:
                self.mouse.device.close()
                self.mouse = None

            if self.joystick and self.joystick_layout != joystick_layout:
                self.joystick.device.close()
                joystick = create_uinput_device(joystick_layout)
                self.joystick = joystick
            elif not self.joystick:
                joystick = create_uinput_device(joystick_layout)
                self.joystick = joystick
                if joystick.device.device:
                    self.logger.info("Created devices {0} (joystick) "
                                     "{1} (evdev) ", joystick.joystick_dev,
                                     joystick.device.device.fn)
            else:
                joystick = None

            if options.udp and not self.server:
                self.server = UDPServer(options.udp_host, options.udp_port)
                self.server.remap = options.udp_remap_buttons
                self.server.send_touch = not options.udp_no_touch
                self.server.start()

            self.joystick.ignored_buttons = set()
            for button in options.ignored_buttons:
                self.joystick.ignored_buttons.add(button)

            if joystick:
                self.joystick_layout = joystick_layout

                # If the profile binding is a single button we don't want to
                # send it to the joystick at all
                if (self.controller.profiles and
                    self.controller.default_profile.profile_toggle and
                    len(self.controller.default_profile.profile_toggle) == 1):

                    button = self.controller.default_profile.profile_toggle[0]
                    self.joystick.ignored_buttons.add(button)
        except DeviceError as err:
            self.controller.exit("Failed to create input device: {0}", err)

    def emit_mouse(self, report):
        if self.joystick:
            self.joystick.emit_mouse(report)

        if self.mouse:
            self.mouse.emit_mouse(report)

        return True

    def handle_report(self, report):
        if self.server:
            self.server.report(report)

        if self.joystick:
            self.joystick.emit(report)

        if self.mouse:
            self.mouse.emit(report)
