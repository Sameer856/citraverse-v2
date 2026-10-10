"""Read timestamped PSIC recording envelopes produced by RadarDebugTool."""
import struct
from collections import Counter


class RecordingDecoder:
    def __init__(self, stream):
        self.stream = stream
        self.buffer = bytearray()
        self.stats = stream.stats

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while len(self.buffer) >= 16:
            if self.buffer[:4] != b'PSIC':
                del self.buffer[0]
                self.stats['recording_resync_bytes'] += 1
                continue
            timestamp, length = struct.unpack_from('<QI', self.buffer, 4)
            if not 6 <= length <= 262160 or not 1500000000000 < timestamp < 4102444800000:
                del self.buffer[0]
                self.stats['invalid_envelopes'] += 1
                continue
            if len(self.buffer) < 16 + length:
                break
            packet = bytes(self.buffer[16:16+length])
            del self.buffer[:16+length]
            for frame in self.stream.feed(packet):
                frame['host_timestamp_ms'] = timestamp
                frame['time_s'] = timestamp / 1000
                frame['source'] = 'Posture dev kit via RadarDebugTool recording'
                result.append(frame)
        return result


class LiveRecording:
    def __init__(self, path, stream):
        self.port = str(path)
        self.path = path
        self.offset = path.stat().st_size  # Never replay old history as live.
        self.decoder = RecordingDecoder(stream)
        self.stats = stream.stats

    def read_frames(self):
        try:
            with self.path.open('rb') as source:
                source.seek(self.offset)
                data = source.read(262144)
                self.offset = source.tell()
        except PermissionError:
            self.stats['file_busy'] += 1
            return []
        return self.decoder.feed(data)

    def close(self):
        pass
