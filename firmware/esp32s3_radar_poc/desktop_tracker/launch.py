"""Launch the existing desktop tracker with ESP32 Wi-Fi data and USB commands."""
import argparse,json,logging,queue,sys,threading,time,types
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];BUILD=HERE.parent/'build'
sys.path.insert(0,str(BUILD/'tracker_deps'))
p=argparse.ArgumentParser();p.add_argument('--tracker',type=Path,default=REPO.parent/'live_tracker');p.add_argument('--host',default='192.168.1.9');p.add_argument('--port',default='COM8');p.add_argument('--connect',action='store_true');p.add_argument('--smoke',type=int,default=0);args=p.parse_args()
if not (args.tracker/'app.py').exists():raise SystemExit('Old tracker not found: '+str(args.tracker))
# Do not import the legacy module that auto-loads telephone credentials.
call_stub=types.ModuleType('fall_call')
class DisabledCaller:
    def __init__(self):self.results=queue.Queue()
    def notify(self,*a,**k):return 'External calls disabled in ESP32 tracker'
call_stub.FallCaller=DisabledCaller;sys.modules['fall_call']=call_stub
sys.path.insert(0,str(args.tracker))
import app as legacy
from transport import UsbControl,WifiFeed
from tkinter import ttk,messagebox
from control import Control
class BridgeControl(Control):
    def command(self,command,cancel=None,timeout=7):
        self.log('> '+command);reply=self.port.command(command,cancel,timeout);self.log(reply);return reply
legacy.Control=BridgeControl
class Desktop(legacy.App):
    def __init__(self,root):
        self.render_pending=False;self.last_displayed=None;self.total_displayed=0
        super().__init__(root)
        root.title('Possumic Live Tracker - ESP32 / MRS6240')
        self.port.set(args.host);self.control_name.set(args.port);self.raw_points.set(True);self.snr.set(0)
        self.ports.configure(values=[args.host],width=18)
        self.fall.call_status.set('External calls disabled in this launcher')
        for frame in root.winfo_children():
            for widget in frame.winfo_children():
                if isinstance(widget,ttk.Combobox) and str(widget.cget('textvariable'))==str(self.radar_profile):widget.configure(values=['RS6240'])
                if isinstance(widget,ttk.Label) and widget.cget('text')=='Data port ':widget.configure(text='ESP32 host ')
                if isinstance(widget,ttk.Entry) and str(widget.cget('textvariable'))==str(self.baud):widget.configure(state='disabled')
        row=ttk.Frame(root,padding=6);row.pack(fill='x',before=self.canvas)
        ttk.Label(row,text='Radar command').pack(side='left');self.command_text=legacy.tk.StringVar(value='mmwc version')
        ttk.Entry(row,textvariable=self.command_text,width=55).pack(side='left',padx=8)
        ttk.Button(row,text='Send command',command=lambda:self.control_action([self.command_text.get().strip()],'Command acknowledged')).pack(side='left')
        ttk.Button(row,text='Start only',command=lambda:self.control_action(['mmwc start','mmwc report points 0'],'Radar started; points enabled')).pack(side='left',padx=5)
        ttk.Label(row,text='USB control / SPI data via ESP32 Wi-Fi').pack(side='left')
        self.root.after(1000,self.save_state)
    def load(self,path=None):
        if path is not None and not Path(path).exists():return
        return super().load(path)
    def refresh_ports(self):
        self.control_ports.configure(values=[p.device for p in legacy.list_ports.comports()])
    def connect(self):
        if self.control_busy:return
        self.disconnect()
        try:self.control_port=UsbControl(self.control_name.get());self.serial=WifiFeed(self.port.get())
        except Exception as e:self.disconnect();messagebox.showerror('ESP32 connection',str(e));return
        self.stream=self.serial;self.mode='live';self.reset_tracks();self.fall.reset('LIVE MRS6240 / ESP32')
        self.received=time.monotonic();self.stop_event=threading.Event();self.control_status.set('USB control ready')
        self.worker=threading.Thread(target=self.read,args=(self.serial,self.stop_event,None),daemon=True);self.worker.start()
    def read(self,feed,stop,unused):
        try:
            while not stop.is_set():
                for frame in feed.read_frames(legacy.points):
                    try:self.events.put_nowait(frame)
                    except queue.Full:feed.stats['queue_drops']+=1
        except Exception as e:
            if not stop.is_set():
                try:self.events.put_nowait(str(e))
                except queue.Full:pass
    def start_radar(self):
        self.control_action(['mmwc stop','mmwc comtype 1','mmwc mode 4 2','mmwc mode get','mmwc freq 58000','mmwc range 20480 80','mmwc veloc 3200 200','mmwc dop_fft 1','mmwc dop_fft get','mmwc coord cart','mmwc frame 50 0','mmwc report points 0','mmwc start','mmwc report points 0'],'SPI configuration applied; radar started')
    def read_settings(self):
        self.control_action(['mmwc version','mmwc mode get','mmwc freq get','mmwc range get','mmwc veloc get','mmwc frame get','mmwc dop_fft get'],'Settings received',diagnostic=True)
    def show(self,frame,t):
        self.last_displayed=frame['frame'];self.total_displayed+=1
        if frame.get('age_ms',0)>350:
            self.fall.detector.reset();self.fall.status.set('Delayed frame: detection history cleared');return
        super().show(frame,t)
    def draw(self):
        if self.render_pending:return
        self.render_pending=True;self.root.after_idle(self.render)
    def render(self):
        self.render_pending=False;super().draw()
    def save_state(self):
        state={'mode':self.mode,'title':self.root.title(),'frame':self.last_displayed,'displayed':self.total_displayed,'stats':dict(self.stream.stats) if hasattr(self,'stream') else {},'details':self.info.cget('text'),'control_status':self.control_status.get(),'control_log':self.control_log[-15:],'external_calls':False}
        (BUILD/'desktop_tracker_state.json').write_text(json.dumps(state,indent=2),encoding='utf-8');self.root.after(1000,self.save_state)
legacy.setup_logging();root=legacy.tk.Tk();desktop=Desktop(root)
if args.connect:root.after(300,desktop.connect)
if args.smoke:
    root.after(2500,lambda:desktop.control_action(['mmwc version'],'USB version verified'))
    root.after(args.smoke*1000,desktop.close)
root.mainloop()
