"""Existing fall tracker fed by the vendor tool's live, timestamped raw log."""
import argparse
import json
import queue
import sys
import threading
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BUILD = HERE.parent / 'build'
sys.path.insert(0, str(BUILD / 'tracker_deps'))
parser = argparse.ArgumentParser()
parser.add_argument('--recording', type=Path)
parser.add_argument('--library', type=Path, default=REPO.parent/'resources/hif_library/HifMsgDataCollectionLib.dll')
parser.add_argument('--tracker', type=Path, default=REPO.parent / 'live_tracker')
args = parser.parse_args()
stub = types.ModuleType('fall_call')
class DisabledCaller:
    def __init__(self): self.results = queue.Queue()
    def notify(self, *a, **k): return 'External calls disabled in dev-kit tracker'
stub.FallCaller = DisabledCaller
sys.modules['fall_call'] = stub
sys.path.insert(0, str(args.tracker))
import app as legacy
from tkinter import ttk
from devkit_feed import LiveRecording
from direct_spi import DirectSpi
import fall_ui
import fall_detection
from presence_tracker import PresenceTracker
from presence_preview import PresencePreview
legacy.Tracker = PresenceTracker
fall_detection.Tracker = PresenceTracker

class DevKitRoom(fall_ui.RoomView):
    def draw(self):
        self.capture()
        if getattr(self,'paint_pending',False): return
        self.paint_pending=True
        self.canvas.after(33,self.paint_latest)

    def paint_latest(self):
        self.paint_pending=False
        if not self.canvas.winfo_exists(): return
        super().draw()
        for item in self.canvas.find_all():
            if self.canvas.type(item) == 'text' and self.canvas.itemcget(item,'text') == 'RS6130':
                self.canvas.itemconfigure(item,text='MRS6240')

fall_ui.RoomView = DevKitRoom

class Desktop(legacy.App):
    def load(self, path=None):
        # Do not auto-load the old sensor recording during initialization.
        if path is not None: return
        return super().load()

    def __init__(self, root):
        self.presence_preview = PresencePreview()
        self.displayed = 0
        self.last_frame = None
        self.last_age_ms = None
        self.max_age_ms = 0
        self.paint_pending = False
        self.file_age_ms = None
        self.ui_queue_ms = None
        super().__init__(root)
        root.title('Possumic Fall Tracker - Posture dev kit' + (' (buffered preview)' if args.recording else ' / direct SPI'))
        self.port.set('Dev kit / vendor recording' if args.recording else 'CH347 direct SPI')
        self.raw_points.set(True)
        self.snr.set(0)
        self.fall.call_status.set(('Buffered dev-kit preview (up to 1.5 s)' if args.recording else 'Direct SPI acquisition')+' — external calls disabled')
        for panel in root.winfo_children():
            for widget in panel.winfo_children():
                if isinstance(widget, ttk.Button):
                    label = widget.cget('text')
                    if label in ('Read version','Configure + Start','Stop Radar','Read settings','Refresh ports'):
                        widget.configure(state='disabled')
                    elif label == 'Connect both': widget.configure(text='Connect dev kit')
                if isinstance(widget, (ttk.Entry, ttk.Combobox)):
                    widget.configure(state='disabled')
        self.root.after(1000, self.save_state)

    def connect(self):
        self.disconnect()
        try: self.serial = LiveRecording(args.recording, legacy.Stream()) if args.recording else DirectSpi(args.library,legacy.points)
        except OSError as e:
            self.status.set('Cannot open vendor recording: '+str(e)); return
        self.stream = self.serial
        self.stop_event = threading.Event()
        self.mode = 'live'
        self.reset_tracks()
        self.fall.reset('POSTURE DEV KIT / '+('BUFFERED PREVIEW' if args.recording else 'DIRECT SPI')+' — verify mounting')
        self.received = time.monotonic()
        self.control_status.set('Radar control remains in RadarDebugTool; Auto save must stay enabled' if args.recording else 'Direct SPI active — keep RadarDebugTool disconnected')
        self.worker = threading.Thread(target=self.read, args=(self.serial,self.stop_event), daemon=True)
        self.worker.start()

    def read(self, feed, stop):
        try:
            while not stop.is_set():
                for frame in feed.read_frames():
                    frame['file_arrival_age_ms'] = time.time()*1000-frame['host_timestamp_ms']
                    try: self.events.put_nowait(frame)
                    except queue.Full: feed.stats['queue_drops'] += 1
                if args.recording: stop.wait(.01)
        except Exception as e:
            if not stop.is_set():
                try: self.events.put_nowait(str(e))
                except queue.Full: pass

    def show(self, frame, t):
        if self.mode == 'live':
            age = time.time()*1000-frame['host_timestamp_ms']
            self.last_age_ms = round(age,1)
            self.file_age_ms = round(frame.get('file_arrival_age_ms',age),1)
            self.ui_queue_ms = round(age-self.file_age_ms,1)
            self.max_age_ms = max(self.max_age_ms,age)
            # Vendor file output is buffered. Analyze by original source time,
            # with an explicit bounded delay; never retimestamp a backlog as now.
            if age < -100 or age > (1500 if args.recording else 350):
                self.stream.stats['stale_frames'] += 1
                self.fall.detector.reset()
                self.current=[]; self.tracks={}; self.display_history.clear()
                self.fall.status.set('Delayed data — detection history cleared')
                self.fall.render(); self.draw()
                return
        self.displayed += 1
        self.last_frame = frame['frame']
        super().show(frame,t)
        burst, age = self.presence_preview.update([p for p in self.current if p['cloud']=='presence'], t)
        if self.presence.get() and burst:
            self.current = [p for p in self.current if p['cloud']!='presence'] + list(burst)
            self.info.configure(text=self.info.cget('text')+f' | Presence preview: {len(burst)} points, age {age*1000:.0f} ms')
        retained = [q for q in self.tracker.tracks.values() if q['last'] < t]
        if retained:
            age = min(t-q['last'] for q in retained)
            self.info.configure(text=self.info.cget('text')+f' | {len(retained)} recently seen (latest {age:.1f}s ago; not fresh detection)')
            # Keep the location marker across burst gaps, not old point clouds or fall samples.
            self.tracks = dict(self.tracker.tracks)

    def draw(self):
        if self.paint_pending: return
        self.paint_pending=True
        self.root.after(33,self.paint_latest)

    def paint_latest(self):
        self.paint_pending=False
        if self.canvas.winfo_exists(): super().draw()

    def save_state(self):
        BUILD.mkdir(exist_ok=True)
        state = dict(mode=self.mode,frame=self.last_frame,displayed=self.displayed,
                     stats=dict(self.stream.stats) if hasattr(self,'stream') else {},
                     details=self.info.cget('text'),armed=self.fall.armed.get(),
                     last_age_ms=self.last_age_ms,max_age_ms=round(self.max_age_ms,1),
                     file_age_ms=self.file_age_ms,ui_queue_ms=self.ui_queue_ms,
                     source=str(args.recording) if args.recording else 'direct CH347 SPI',external_calls=False)
        (BUILD/'devkit_tracker_state.json').write_text(json.dumps(state,indent=2))
        self.root.after(1000,self.save_state)

legacy.setup_logging()
root=legacy.tk.Tk()
desktop=Desktop(root)
root.after(300,desktop.connect)
root.after(600,desktop.fall.open)
root.mainloop()
