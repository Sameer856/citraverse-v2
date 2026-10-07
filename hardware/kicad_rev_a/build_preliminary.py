"""Generate the explicitly unfinished Rev A placement/interface review in KiCad 10.

Run with KiCad's bundled Python. No production manufacturing outputs are generated.
"""
from pathlib import Path
import json
import math
import re
import uuid
import pcbnew as p

ROOT = Path(__file__).resolve().parent
LIB = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport')
NAME = 'citraverse_rev_a_PRELIMINARY'
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / 'preview').mkdir(exist_ok=True)
uid = lambda: str(uuid.uuid4())
q = lambda s: json.dumps(str(s))
xy = lambda x,y: p.VECTOR2I(p.FromMM(x),p.FromMM(y))

def parse(text):
    tokens = iter(re.findall(r'"(?:\\.|[^"\\])*"|[^\s()]+|[()]',text))
    def item(tok):
        if tok != '(':
            return json.loads(tok) if tok.startswith('"') else tok
        out=[]
        for t in tokens:
            if t==')': return out
            out.append(item(t))
    return item(next(tokens))

def child(node,key):
    return next(v for v in node if isinstance(v,list) and v and v[0]==key)

libtree = parse((LIB/'symbols/RF_Module.kicad_sym').read_text())
esp = next(v for v in libtree if isinstance(v,list) and v[:2]==['symbol','ESP32-S3-WROOM-1'])
espunit = next(v for v in esp if isinstance(v,list) and v[:2]==['symbol','ESP32-S3-WROOM-1_1_1'])
esp_pins = [(child(v,'number')[1],child(v,'name')[1],v[1]) for v in espunit if isinstance(v,list) and v[0]=='pin']
gpio={4:'SD_CS',5:'SD_CLK',6:'SD_MISO',7:'SD_MOSI',9:'RADAR_PA5',10:'RADAR_CS',11:'RADAR_MOSI',12:'RADAR_CLK',13:'RADAR_MISO',14:'RADAR_PA4',15:'I2S_BCLK',16:'I2S_WS',17:'MIC_DOUT',2:'SPK_DIN',43:'FACTORY_UART_TX',44:'FACTORY_UART_RX',18:'RADAR_RX_AT_MODULE',21:'RADAR_TX_AT_MODULE',19:'USB_D-',20:'USB_D+',47:'RADAR_PA11_RESERVED',48:'RADAR_NRST',8:'RADAR_POWER_EN',38:'STATUS_LED',1:'BOARD_NTC',0:'BOOT_SERVICE'}
esp_nets={}
for num,name,kind in esp_pins:
    if name=='GND': esp_nets[num]='GND'
    elif name=='3V3': esp_nets[num]='3V3'
    elif name=='EN': esp_nets[num]='ESP_EN'
    elif name.startswith('IO') and name[2:].isdigit() and int(name[2:]) in gpio: esp_nets[num]=gpio[int(name[2:])]

# Each tuple: reference, value, footprint, pins [(number,name,type)], pin-net map,
# schematic center, board location, board rotation. Only the power block is a no-pad placeholder.
parts=[]
def add(ref,value,fp,pins,nets,spos,bpos,rot=0):
    parts.append(dict(ref=ref,value=value,fp=fp,pins=pins,nets=nets,spos=spos,bpos=bpos,rot=rot,id=uid()))
add('U1','ESP32-S3-WROOM-1-N16R8','RF_Module:ESP32-S3-WROOM-1',esp_pins,esp_nets,(65,80),(100,74))
radarnames=['PA11_RESERVED','PA6_RESERVED','PB1_UART_RX','PB0_UART_TX','NRST','GND','VCC_3V3','VDDIO_3V3','PA5_SPI_WP','PA4_SPI_HOLD','PA3_SPI_MISO','PA2_SPI_MOSI','PA1_SPI_CLK','PA0_SPI_CS','GND','V13_NO_LOAD']
radarnets={str(k):v for k,v in {1:'RADAR_PA11_RESERVED',3:'RADAR_RX_AT_MODULE',4:'RADAR_TX_AT_MODULE',5:'RADAR_NRST',6:'GND',7:'RADAR_3V3',8:'RADAR_3V3',9:'RADAR_PA5',10:'RADAR_PA4',11:'RADAR_MISO',12:'RADAR_MOSI',13:'RADAR_CLK',14:'RADAR_CS',15:'GND'}.items()}
add('U2','MRS6240-P2512 - guide-derived 16-pin THT footprint','Citraverse:MRS6240_P2512_GUIDE_DERIVED',[(str(i+1),n,'passive') for i,n in enumerate(radarnames)],radarnets,(170,58),(100,104))
sdnames=['DAT2_NC','DAT3_CS','CMD_MOSI','VDD','CLK','VSS','DAT0_MISO','DAT1_NC','SWITCH_1_RESERVED','SWITCH_2_RESERVED']
add('J1','microSD Hirose DM3AT-SF-PEJM5 candidate','Connector_Card:microSD_HC_Hirose_DM3AT-SF-PEJM5',[(str(i+1),n,'passive') for i,n in enumerate(sdnames)]+[('SH','SHIELD','passive')],{'2':'SD_CS','3':'SD_MOSI','4':'3V3','5':'SD_CLK','6':'GND','7':'SD_MISO','SH':'GND'},(170,115),(73,109),-90)
usbpins=[(n,s,'passive') for n,s in [('A1','GND'),('A4','VBUS'),('A5','CC1'),('A6','D+'),('A7','D-'),('A8','SBU1'),('A9','VBUS'),('A12','GND'),('B1','GND'),('B4','VBUS'),('B5','CC2'),('B6','D+'),('B7','D-'),('B8','SBU2'),('B9','VBUS'),('B12','GND'),('S1','SHIELD')]]
usbnet={n:({'GND':'GND','VBUS':'USB_5V','CC1':'USB_CC1','CC2':'USB_CC2','D+':'USB_D+','D-':'USB_D-','SHIELD':'GND'}.get(s)) for n,s,_ in usbpins}
usbnet={n:v for n,v in usbnet.items() if v}
add('J2','USB-C 5V input / native USB','Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',usbpins,usbnet,(280,58),(138,101),90)
# Common six-pin breakout module, viewed at its connector: VDD, GND, L/R, SD, WS, SCK.
micpins=[('1','VDD','power_in'),('2','GND','power_in'),('3','L_R','input'),('4','SD','output'),('5','WS','input'),('6','SCK','input')]
add('U3','INMP441 6-pin breakout module','Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',micpins,{'1':'3V3','2':'GND','3':'GND','4':'MIC_DOUT','5':'I2S_WS','6':'I2S_BCLK'},(170,158),(94,132),90)
powerpins=[('1','USB_5V_IN','passive'),('2','3V3_MAIN_OUT','passive'),('3','GND','passive'),('4','RADAR_ENABLE','passive'),('5','RADAR_3V3_OUT','passive')]
add('PS1','POWER BLOCK UNDESIGNED 5V to 3V3 >=2A','Citraverse:POWER_UNDESIGNED_NO_PADS',powerpins,{'1':'USB_5V','2':'3V3','3':'GND','4':'RADAR_POWER_EN','5':'RADAR_3V3'},(280,112),(125,117))
for ref,val,net,spos,bpos in [('R1','5.1k USB-C CC1','USB_CC1',(250,154),(128,94)),('R2','5.1k USB-C CC2','USB_CC2',(295,154),(128,97)),('R3','10k EN pull-up','ESP_EN',(250,178),(110,88)),('R4','10k BOOT pull-up','BOOT_SERVICE',(295,178),(110,91)),('R5','100k INMP441 SD pulldown','MIC_DOUT',(40,222),(82,120)),('R6','0R INMP441 left select','GND',(85,222),(82,122)),('R7','10k INMP441 enable','3V3',(130,222),(82,124))]:
    other='GND' if ref in ['R1','R2'] else '3V3'
    add(ref,val,'Resistor_SMD:R_0603_1608Metric',[('1','1','passive'),('2','2','passive')],{'1':net,'2':other},spos,bpos)
for ref,val,net,spos,bpos in [('C1','10uF ESP32 bulk','3V3',(40,161),(87,87)),('C2','100nF ESP32 local','3V3',(85,161),(90,87)),('C3','1uF EN delay','ESP_EN',(40,185),(110,94)),('C4','100nF radar local','RADAR_3V3',(85,185),(96,114)),('C5','10uF radar bulk','RADAR_3V3',(40,209),(92,114)),('C6','100nF SD local','3V3',(85,209),(73,105)),('C7','100nF INMP441 VDD','3V3',(40,233),(87,123)),('C8','1uF INMP441 bulk','3V3',(85,233),(90,123)),('C9','10uF speaker amp bulk','5V_PROTECTED',(130,233),(118,116)),('C10','100nF speaker amp local','5V_PROTECTED',(175,233),(121,116))]:
    add(ref,val,'Capacitor_SMD:C_0603_1608Metric',[('1','1','passive'),('2','2','passive')],{'1':net,'2':'GND'},spos,bpos)
service=[('1','GND','passive'),('2','3V3','passive'),('3','EN','passive'),('4','BOOT','passive'),('5','UART_TX','passive'),('6','UART_RX','passive')]
add('J4','Factory pogo: GND 3V3 EN BOOT TX RX','Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',service,{'1':'GND','2':'3V3','3':'ESP_EN','4':'BOOT_SERVICE','5':'FACTORY_UART_TX','6':'FACTORY_UART_RX'},(170,203),(77,128),90)
speakerpins=[('1','SPK+','passive'),('2','SPK-','passive')]
add('J5','JST-PH speaker output (from MAX98357A)','Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical',speakerpins,{'1':'SPK_P','2':'SPK_N'},(230,203),(122,124),180)
amppins=[(str(n),name,'passive') for n,name in [(1,'DIN'),(2,'GAIN_SLOT'),(3,'OUTN'),(4,'LRCLK'),(5,'GND'),(6,'BCLK'),(7,'VDD'),(8,'VDD'),(9,'OUTP'),(10,'NC'),(11,'GND'),(12,'NC'),(13,'NC'),(14,'NC'),(15,'NC'),(16,'SD_MODE'),('EP','EP_GND')]]
add('U4','MAX98357AETE+ I2S Class-D speaker amplifier','Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.45x1.45mm',amppins,{'1':'SPK_DIN','2':'GND','3':'SPK_N','4':'I2S_WS','5':'GND','6':'I2S_BCLK','7':'5V_PROTECTED','8':'5V_PROTECTED','9':'SPK_P','11':'GND','16':'3V3','EP':'GND'},(230,160),(121,119))

board=p.BOARD(); board.SetCopperLayerCount(4)
board.GetDesignSettings().SetBoardThickness(p.FromMM(1.6))
nets={}
for name in sorted({v for c in parts for v in c['nets'].values()}):
    n=p.NETINFO_ITEM(board,name);board.Add(n);nets[name]=n
def text(value,x,y,size=1.2,layer=p.F_SilkS):
    t=p.PCB_TEXT(board);t.SetText(value);t.SetPosition(xy(x,y));t.SetTextSize(xy(size,size));t.SetTextThickness(p.FromMM(.15));t.SetLayer(layer);board.Add(t)
def rect(x1,y1,x2,y2,layer=p.Dwgs_User):
    s=p.PCB_SHAPE();s.SetShape(p.SHAPE_T_RECT);s.SetStart(xy(x1,y1));s.SetEnd(xy(x2,y2));s.SetLayer(layer);s.SetWidth(p.FromMM(.2));board.Add(s)
def mrs6240_footprint():
    """Guide-derived MRS6240-P2512 footprint, Figure 7-2 (all dimensions in mm)."""
    fp=p.FOOTPRINT(board)
    fp.SetReference('U2');fp.SetValue('MRS6240-P2512')
    # 12.00 x 25.00 module body; pin 1 marker is at the lower-left in top view.
    shape=p.PCB_SHAPE(fp);shape.SetShape(p.SHAPE_T_RECT);shape.SetStart(xy(-6,-12.5));shape.SetEnd(xy(6,12.5));shape.SetLayer(p.F_SilkS);shape.SetWidth(p.FromMM(.15));fp.Add(shape)
    marker=p.PCB_SHAPE(fp);marker.SetShape(p.SHAPE_T_CIRCLE);marker.SetCenter(xy(-5.3,11.7));marker.SetEnd(xy(-5.0,11.7));marker.SetLayer(p.F_SilkS);marker.SetWidth(p.FromMM(.15));fp.Add(marker)
    # Figure 7-2: 16 PTH pads, 1.27 pitch, 0.90 x 2.15 pad, 0.65 drill.
    # X0 derives from the 1.56 edge datum plus half the 0.90 pad width.
    x0=-3.99
    for index in range(16):
        top=index >= 8;col=(index-8) if top else index
        pad=p.PAD(fp);pad.SetNumber(str(index+1));pad.SetAttribute(p.PAD_ATTRIB_PTH);pad.SetShape(p.PAD_SHAPE_OVAL)
        pad.SetSize(xy(.90,2.15));pad.SetDrillSize(xy(.65,.65))
        pad.SetFPRelativePosition(xy(x0+col*1.27, -10.925 if top else 10.925));fp.Add(pad)
    return fp
def inmp441_footprint():
    """Bare INMP441 LGA_CAV footprint from the manufacturer's package geometry."""
    fp=p.FOOTPRINT(board);fp.SetReference('U3');fp.SetValue('INMP441ACEZ-R7')
    body=p.PCB_SHAPE(fp);body.SetShape(p.SHAPE_T_RECT);body.SetStart(xy(-2.36,-1.88));body.SetEnd(xy(2.36,1.88));body.SetLayer(p.F_SilkS);body.SetWidth(p.FromMM(.12));fp.Add(body)
    # Bottom port opening - no copper or solder mask below the acoustic port.
    port=p.PCB_SHAPE(fp);port.SetShape(p.SHAPE_T_CIRCLE);port.SetCenter(xy(0,0));port.SetEnd(xy(.78,0));port.SetLayer(p.F_SilkS);port.SetWidth(p.FromMM(.12));fp.Add(port)
    # 9-terminal LGA_CAV: outer rows are 0.40 x 0.60 mm; centre ground pad is enlarged.
    pad_pos={1:(-1.55,-1.20),2:(-1.55,-.40),3:(-1.55,.40),4:(-1.55,1.20),5:(0,0),6:(1.55,1.20),7:(1.55,.40),8:(1.55,-.40),9:(1.55,-1.20)}
    for number,(x,y) in pad_pos.items():
        pad=p.PAD(fp);pad.SetNumber(str(number));pad.SetAttribute(p.PAD_ATTRIB_SMD);pad.SetShape(p.PAD_SHAPE_RECT)
        pad.SetSize(xy(.40,.60) if number!=5 else xy(.90,.90));pad.SetFPRelativePosition(xy(x,y))
        layers=p.LSET();layers.AddLayer(p.F_Cu);layers.AddLayer(p.F_Paste);layers.AddLayer(p.F_Mask);pad.SetLayerSet(layers);fp.Add(pad)
    return fp
circle=p.PCB_SHAPE();circle.SetShape(p.SHAPE_T_CIRCLE);circle.SetCenter(xy(100,100));circle.SetEnd(xy(140,100));circle.SetLayer(p.Edge_Cuts);circle.SetWidth(p.FromMM(.05));board.Add(circle)
projectid=uid()
for c in parts:
    if c['fp']=='Citraverse:MRS6240_P2512_GUIDE_DERIVED':
        fp=mrs6240_footprint()
    elif c['fp'].startswith('Citraverse:'):
        fp=p.FOOTPRINT(board)
        w,h=(16,13)
        x,y=c['bpos'];rect(x-w/2,y-h/2,x+w/2,y+h/2)
        text('POWER\nDESIGN TBD',x,y,1,p.Dwgs_User)
    else:
        lib,name=c['fp'].split(':');fp=p.FootprintLoad(str(LIB/'footprints'/f'{lib}.pretty'),name)
        if not fp: raise ValueError(c['fp'])
    fp.SetReference(c['ref']);fp.SetValue(c['value']);fp.SetPosition(xy(*c['bpos']));fp.SetOrientationDegrees(c['rot'])
    fp.SetPath(p.KIID_PATH('/'+projectid+'/'+c['id']))
    for pad in fp.Pads():
        if pad.GetNumber() in c['nets']:pad.SetNet(nets[c['nets'][pad.GetNumber()]])
    board.Add(fp)
    fp.Reference().SetTextSize(xy(1,1));fp.Value().SetVisible(False)
for i,(x,y) in enumerate([(72,82),(128,82),(72,118)],1):
    fp=p.FootprintLoad(str(LIB/'footprints/MountingHole.pretty'),'MountingHole_2.7mm_M2.5');fp.SetReference('H'+str(i));fp.SetPosition(xy(x,y));board.Add(fp)
# Additional radio keepout is intentionally conservative; tune only after enclosure review.
zone=p.ZONE(board);zone.SetIsRuleArea(True);zone.SetLayerSet(p.LSET.AllCuMask());zone.SetDoNotAllowTracks(True);zone.SetDoNotAllowVias(True);zone.SetDoNotAllowZoneFills(True);zone.SetDoNotAllowPads(False);zone.SetDoNotAllowFootprints(False)
poly=zone.Outline();poly.NewOutline()
for x,y in [(87,65),(113,65),(113,69),(87,69)]:poly.Append(int(p.FromMM(x)),int(p.FromMM(y)))
board.Add(zone)
text('INMP441',94,136,0.7)
text('SD',65,94,0.8)
text('USB-C',133,112,0.8)
text('80 mm REV A - UNROUTED',100,145,0.8,p.Dwgs_User)
p.SaveBoard(str(ROOT/(NAME+'.kicad_pcb')),board)
project=json.loads((LIB/'template/kicad.kicad_pro').read_text())
project['meta']={'filename':NAME+'.kicad_pro','version':1}
project['text_variables']={'STATUS':'PRELIMINARY / NOT FOR FABRICATION'}
(ROOT/(NAME+'.kicad_pro')).write_text(json.dumps(project,indent=2))

# Self-contained interface schematic: custom rectangular symbols, official ESP pad numbers.
libparts=[]; instances=[]; labels=[]
for c in parts:
    ident=c['ref']; pins=c['pins']; count=math.ceil(len(pins)/2); hh=max(5.08,(count+1)*1.27); hw=15.24
    syms=[f'(symbol "{ident}_0_1" (rectangle (start {-hw} {hh}) (end {hw} {-hh}) (stroke (width 0.254) (type default)) (fill (type background))))']
    pinstr=[]; pinloc=[]
    for i,(num,name,kind) in enumerate(pins):
        left=i<count; row=i if left else i-count
        x=-17.78 if left else 17.78;y=(count-1)*1.27-row*2.54;angle=0 if left else 180
        pinstr.append(f'(pin {kind} line (at {x} {y} {angle}) (length 2.54) (name {q(name)} (effects (font (size 1 1)))) (number {q(num)} (effects (font (size .9 .9)))))')
        pinloc.append((num,x,y,left))
    syms.append(f'(symbol "{ident}_1_1" '+''.join(pinstr)+')')
    libparts.append(f'(symbol "Citraverse:{ident}" (pin_names (offset .508)) (in_bom yes) (on_board yes) (property "Reference" {q(ident)} (at 0 {hh+2.54} 0) (effects (font (size 1.27 1.27)))) (property "Value" {q(c["value"])} (at 0 {-hh-2.54} 0) (effects (font (size 1 1)))) '+''.join(syms)+')')
    x,y=c['spos']
    instances.append(f'(symbol (lib_id "Citraverse:{ident}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes) (dnp no) (uuid "{c["id"]}") (property "Reference" {q(ident)} (at {x} {y-hh-2.54} 0) (effects (font (size 1.27 1.27)))) (property "Value" {q(c["value"])} (at {x} {y+hh+2.54} 0) (effects (font (size .9 .9)))) (property "Footprint" {q(c["fp"])} (at {x} {y} 0) (effects (font (size 1 1)) hide)) (instances (project {q(NAME)} (path "/{projectid}" (reference {q(ident)}) (unit 1)))))')
    for num,px,py,left in pinloc:
        lx,ly=x+px,y-py
        if num in c['nets']:
            # Label reaches outward from each pin, keeping the pin name readable.
            justify='right' if left else 'left'
            labels.append(f'(label {q(c["nets"][num])} (at {lx} {ly} 0) (effects (font (size .85 .85)) (justify {justify} bottom)) (uuid "{uid()}"))')
        else:labels.append(f'(no_connect (at {lx} {ly}) (uuid "{uid()}"))')
notes=[('INTERFACE / PLACEMENT REVIEW ONLY - NOT FOR FABRICATION',30,20),('Radar footprint is derived from the supplied MRS6240 guide: 12 x 25 mm, 16 THT pads, 1.27 mm pitch.',30,233),('Radar SPI role and IRQ behavior require firmware/tool validation.',30,239),('Power protection, buck, load switch, reset behavior, LED and NTC circuits remain to be designed.',30,245),('INMP441 adapter pinout is a proposed carrier contract; verify the purchased microphone module.',30,251),('Four copper layers; 90 mm circular outline is an initial mechanical proposal. No tracks routed.',30,257)]
noteforms=[f'(text {q(s)} (at {x} {y} 0) (effects (font (size 1.27 1.27)) (justify left)) (uuid "{uid()}"))' for s,x,y in notes]
sch=f'(kicad_sch (version 20250114) (generator "citraverse_preliminary") (uuid "{projectid}") (paper "A3") (lib_symbols '+''.join(libparts)+')'+''.join(instances+labels+noteforms)+')\n'
(ROOT/(NAME+'.kicad_sch')).write_text(sch)
(ROOT/'pin_contract.json').write_text(json.dumps([{k:v for k,v in c.items() if k not in ['id']} for c in parts],indent=2))
print('Created',NAME,'with',len(parts),'interface components. Board is UNROUTED; the power block has no pads.')
