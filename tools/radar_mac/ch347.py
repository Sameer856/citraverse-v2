"""Small ctypes boundary to our C adapter, compiled against WCH's macOS SDK."""
import ctypes as C
import time
from pathlib import Path


class CH347:
    def __init__(self):
        path = Path(__file__).parent / 'build/libcitra_ch347.dylib'
        if not path.exists():
            raise RuntimeError('Run Setup Mac.command first to install the native USB adapter.')
        self.lib = C.CDLL(str(path))
        self.lib.citra_init.restype = C.c_int
        self.lib.citra_devices.argtypes = [C.c_void_p, C.c_int]
        self.lib.citra_open.argtypes = [C.c_uint32, C.c_int, C.c_int]
        self.lib.citra_xfer.argtypes = [C.c_uint32, C.c_int, C.c_void_p, C.c_int]
        self.lib.citra_gpio.argtypes = [C.c_uint32]
        self.lib.citra_input.argtypes = [C.c_uint32, C.c_int]
        self.lib.citra_close.argtypes = [C.c_uint32]
        self.lib.citra_close.restype = None
        if self.lib.citra_init() < 0:
            raise RuntimeError('WCH USB library initialization failed')
        self.handle = None
        self.cs = 0

    def devices(self):
        buf = C.create_string_buffer(8192)
        if self.lib.citra_devices(buf, len(buf)) < 0:
            raise RuntimeError('WCH USB enumeration failed')
        return [dict(zip(('handle', 'vid', 'pid', 'interface', 'mode'), row.split(',')))
                for row in buf.value.decode().splitlines()]

    def open(self, handle, clock=6, cs=0, irq=-1):
        if self.handle is not None:
            raise RuntimeError('USB device already open')
        rc = self.lib.citra_open(int(handle), clock, cs)
        if rc != 0:
            raise RuntimeError(f'Cannot open/configure CH347 (error {rc}); close other radar tools.')
        self.handle, self.cs = int(handle), cs
        if irq >= 0 and self.lib.citra_input(self.handle, irq) != 0:
            self.close()
            raise RuntimeError('Cannot configure selected Notify GPIO as input')
        time.sleep(.05)

    def xfer(self, data):
        if self.handle is None:
            raise RuntimeError('USB is closed')
        buf = (C.c_ubyte * len(data)).from_buffer_copy(data)
        if self.lib.citra_xfer(self.handle, self.cs, buf, len(data)) != len(data):
            raise RuntimeError('CH347 SPI transfer failed or device disconnected')
        return bytes(buf)

    def gpio(self):
        value = self.lib.citra_gpio(self.handle)
        if value < 0:
            raise RuntimeError('CH347 GPIO read failed')
        return value

    def close(self):
        if self.handle is not None:
            self.lib.citra_close(self.handle)
            self.handle = None
