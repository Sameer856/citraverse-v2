"""Existing fall tracker fed by the vendor tool's live, timestamped raw log."""
import argparse
import json
import queue
import sys
import threading
import time
import types
import copy
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BUILD = HERE.parent / 'build'
sys.path.insert(0, str(BUILD / 'tracker_deps'))
parser = argparse.ArgumentParser()
parser.add_argument('--recording', type=Path)
parser.add_argument('--presence-only', action='store_true', help='Exclude motion from tracking and fall inputs, not only drawing')
parser.add_argument('--library', type=Path, default=REPO.parent/'resources/hif_library/HifMsgDataCollectionLib.dll')
parser.add_argument('--tracker', type=Path, default=REPO.parent / 'live_tracker')
parser.add_argument('--seat', nargs=3, type=float, metavar=('ID','X','Y'))
parser.add_argument('--presence-audit', type=Path)
parser.add_argument('--seat-calibration', type=Path, help='Fixed empty-seat point-count calibration; selected region only')
parser.add_argument('--spatial-model', type=Path, help='Frozen 3-D spatial/temporal presence model; laptop development mode')
args = parser.parse_args()
spatial_model = None
if args.spatial_model:
    if not args.presence_only or args.seat_calibration or not args.seat:
        parser.error('--spatial-model requires --presence-only and --seat; cannot combine count calibration')
    spatial_model = json.loads(args.spatial_model.read_text())
calibration = None
if args.seat_calibration:
    try:
        calibration = json.loads(args.seat_calibration.read_text())
        if (not args.presence_only or not args.seat
                or calibration['method'] not in ('fixed_empty_seat_max_plus_one_v1','fixed_empty_seat_window_v2','fixed_empty_seat_hysteresis_v3')
                or calibration['anchor'] != list(args.seat[1:])
                or calibration['radius_m'] != .5 or calibration['snr_min'] != 18
                or type(calibration['minimum_points']) is not int
                or not 3 <= calibration['minimum_points'] <= 256):
            raise ValueError('calibration does not match selected seat and gates')
        if calibration['method'] in ('fixed_empty_seat_window_v2','fixed_empty_seat_hysteresis_v3') and calibration.get('window_s') != 1.5:
            raise ValueError('window calibration requires bounded 1.5-second history')
        if calibration['method'] == 'fixed_empty_seat_hysteresis_v3' and (calibration['minimum_points'] != 34 or calibration.get('continuation_points') != 26):
            raise ValueError('hysteresis requires validated 34/26 thresholds')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
if args.seat and (not args.presence_only or not all(math.isfinite(v) for v in args.seat)
                  or args.seat[0] < 1 or not args.seat[0].is_integer()):
    parser.error('--seat requires presence-only mode, a positive integer ID and finite XY coordinates')
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
if spatial_model:
    from spatial_adapter import tracker_class
    PresenceTracker = tracker_class(spatial_model)
from presence_preview import PresencePreview
legacy.Tracker = PresenceTracker
fall_detection.Tracker = PresenceTracker

class DevKitRoom(fall_ui.RoomView):
    def capture(self):
        if not getattr(self,'rendering_preview',False): super().capture()
    def draw(self):
        self.capture()
        if getattr(self,'paint_pending',False): return
        self.paint_pending=True
        self.canvas.after(33,self.paint_latest)

    def paint_latest(self):
        self.paint_pending=False
        if not self.canvas.winfo_exists(): return
        original = self.panel
        app = original.app
        preview = copy.copy(original)
        preview.detector = copy.copy(original.detector)
        settings = original.detector.settings
        selected = app.target_view.get()
        source_points = app.current
        shown_age = app.preview_age_text
        if selected != 'All candidates':
            q = app.tracker.tracks.get(int(selected[1:]))
            age = app.tracker.last-q['last'] if q else None
            source_points = q['points'] if q and age <= .35 else []
            shown_age = f'{age*1000:.0f} ms' if age is not None else 'track lost'
            if spatial_model:
                shown_age += ' | 3D presence region | '+(app.tracker.spatial_status or {}).get('state','unobserved')
            elif app.tracker.focus is not None: shown_age += ' | stationary region lock (0.5 m)'
            if (app.tracker.background_minimum is not None and app.tracker.focus is not None
                    and tuple(app.tracker.focus['anchor'][:2]) == app.tracker.background_anchor):
                shown_age += f' | fixed empty-seat gate: {app.tracker.background_minimum} points'
                if app.tracker.background_window:
                    shown_age += f' / {app.tracker.background_window}s; 2 fresh required'
                if app.tracker.background_weak is not None:
                    shown_age += ' | weak continuation limited to 2s'
        # Render a separate snapshot: cloud toggles must never modify fall inputs.
        pts = [
            fall_detection.world_point(p,settings) for p in source_points
            if (app.presence.get() if p['cloud']=='presence' else app.motion.get())]
        preview.detector.world = pts
        preview.detector.histories = {}  # Display track IDs are independent of fall-track IDs.
        preview.detector.visible = {}
        for ident,q in app.tracks.items():
            if app.target_view.get() not in ('All candidates',f'T{ident}'): continue
            members = [fall_detection.world_point(p,settings) for p in q['points']
                       if (app.presence.get() if p['cloud']=='presence' else app.motion.get())]
            if not members: continue
            item = dict(q,points=members)
            center = fall_detection.world_point(dict(zip(('x','y','z'),q['pos'])),settings)
            item['pos'] = [center[k] for k in ('x','y','z')]
            item['trail'] = [item['pos']]
            preview.detector.visible[ident] = item
        # Point inspection stays independent of arming and candidate filtering.
        preview.app = copy.copy(app)
        preview.app.raw_points = types.SimpleNamespace(get=lambda:True)
        self.panel = preview
        self.rendering_preview = True
        try: super().draw()
        finally:
            self.panel = original
            self.rendering_preview = False
        self.canvas.create_text(18,42,anchor='w',fill='#e1e7ed',text=
            f"{selected} | Shown: {sum(p['cloud']=='motion' for p in pts)} motion / {sum(p['cloud']=='presence' for p in pts)} presence | evidence age: {shown_age}")
        for item in self.canvas.find_all():
            if self.canvas.type(item) == 'text':
                label = self.canvas.itemcget(item,'text')
                if label == 'MONITORING' and not original.detector.visible:
                    self.canvas.itemconfigure(item,text='NO FRESH FALL TARGET')
                if label.startswith('Current clusters:'):
                    self.canvas.itemconfigure(item,text=f'Displayed candidates: {len(preview.detector.visible)} | Points: {len(pts)}')
            if self.canvas.type(item) == 'rectangle' and not original.detector.visible and self.canvas.itemcget(item,'fill') == '#27a344':
                self.canvas.itemconfigure(item,fill='#7a8591')
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
        self.preview_age_text = 'none'
        self.displayed = 0
        self.last_frame = None
        self.last_age_ms = None
        self.max_age_ms = 0
        self.paint_pending = False
        self.file_age_ms = None
        self.ui_queue_ms = None
        super().__init__(root)
        root.title('Possumic Fall Tracker - Posture dev kit' + (' (buffered preview)' if args.recording else ' / direct SPI'))
        if args.presence_only: root.title(root.title()+' / PRESENCE-ONLY TRACKING')
        if calibration: root.title(root.title()+' / FIXED EMPTY-SEAT CALIBRATION')
        if spatial_model: root.title(root.title()+' / SPATIAL PRESENCE — LAPTOP FILTER')
        self.port.set('Dev kit / vendor recording' if args.recording else 'CH347 direct SPI')
        self.raw_points.set(True)
        self.snr.set(0)
        self.motion.set(False)
        self.presence.set(True)
        self.target_view = legacy.tk.StringVar(value='All candidates')
        target_row = ttk.Frame(root)
        target_row.pack(fill='x')
        ttk.Label(target_row,text='3D target (filters marker AND point cloud):').pack(side='left')
        self.target_choice = ttk.Combobox(target_row,textvariable=self.target_view,
            values=['All candidates'],state='readonly',width=20)
        self.target_choice.pack(side='left')
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
        self.target_choice.configure(state='readonly')
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
        if args.presence_only and args.seat:
            ident, x, y = args.seat
            self.tracker.reserve_seat(int(ident), x, y)
            if calibration:
                self.tracker.background_minimum = calibration['minimum_points']
                self.tracker.background_anchor = tuple(calibration['anchor'])
                if calibration['method'] in ('fixed_empty_seat_window_v2','fixed_empty_seat_hysteresis_v3'):
                    self.tracker.background_window = calibration['window_s']
                if calibration['method'] == 'fixed_empty_seat_hysteresis_v3':
                    self.tracker.background_weak = calibration['continuation_points']
            self.target_view.set(f'T{int(ident)}')
        self.fall.reset('POSTURE DEV KIT / '+('BUFFERED PREVIEW' if args.recording else 'DIRECT SPI')+' — verify mounting')
        self.received = time.monotonic()
        self.control_status.set('Radar control remains in RadarDebugTool; Auto save must stay enabled' if args.recording else 'Direct SPI active — keep RadarDebugTool disconnected')
        self.worker = threading.Thread(target=self.read, args=(self.serial,self.stop_event), daemon=True)
        self.worker.start()

    def read(self, feed, stop):
        audit = None
        audit_start = time.monotonic()
        try:
            if args.presence_audit: audit = args.presence_audit.open('w',encoding='utf-8')
            while not stop.is_set():
                for frame in feed.read_frames():
                    if audit and time.monotonic()-audit_start <= 660:
                        audit.write(json.dumps(dict(frame=frame['frame'],time_s=frame['time_s'],
                            points=[p for p in frame['points'] if p['cloud']=='presence']))+'\n')
                        audit.flush()
                    frame['file_arrival_age_ms'] = time.time()*1000-frame['host_timestamp_ms']
                    try: self.events.put_nowait(frame)
                    except queue.Full: feed.stats['queue_drops'] += 1
                if args.recording: stop.wait(.01)
        except Exception as e:
            if not stop.is_set():
                try: self.events.put_nowait(str(e))
                except queue.Full: pass
        finally:
            if audit: audit.close()

    def show(self, frame, t):
        if args.presence_only:
            frame = dict(frame,points=[p for p in frame['points'] if p['cloud']=='presence'])
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
        if args.presence_only:
            selected = self.target_view.get()
            self.tracker.focus_presence(None if selected == 'All candidates' else int(selected[1:]))
        super().show(frame,t)
        burst, age = self.presence_preview.update([p for p in self.current if p['cloud']=='presence'], t)
        self.preview_age_text = 'none' if age is None else f'{age*1000:.0f} ms'
        if self.presence.get() and burst:
            self.current = [p for p in self.current if p['cloud']!='presence'] + list(burst)
            self.info.configure(text=self.info.cget('text')+f' | Presence preview: {len(burst)} points, age {age*1000:.0f} ms')
        retained = [q for q in self.tracker.tracks.values() if q['last'] < t]
        if retained:
            age = min(t-q['last'] for q in retained)
            self.info.configure(text=self.info.cget('text')+f' | {len(retained)} recently seen (latest {age:.1f}s ago; not fresh detection)')
            # Keep the location marker across burst gaps, not old point clouds or fall samples.
            self.tracks = dict(self.tracker.tracks)
        self.target_choice.configure(values=['All candidates']+[f'T{i}' for i in self.tracker.tracks])

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
        state['presence_only_tracking'] = args.presence_only
        state['seat_calibration'] = calibration
        if spatial_model:
            state['spatial_model_method'] = spatial_model['method']
            state['spatial_presence'] = {k:v for k,v in (self.tracker.spatial_status or {}).items() if k!='points'}
        state['selected_target'] = self.target_view.get()
        state['stationary_focus_anchor'] = self.tracker.focus['anchor'] if self.tracker.focus else None
        state['saved_at'] = time.time()
        state['tracks'] = {str(i):dict(position=q['pos'],age_s=round(max(0,self.tracker.last-q['last']),3),
                                     state=q['state'],clouds=sorted({p['cloud'] for p in q['points']}))
                           for i,q in self.tracker.tracks.items()}
        (BUILD/'devkit_tracker_state.json').write_text(json.dumps(state,indent=2))
        self.root.after(1000,self.save_state)

legacy.setup_logging()
root=legacy.tk.Tk()
desktop=Desktop(root)
root.after(300,desktop.connect)
root.after(600,desktop.fall.open)
root.mainloop()
