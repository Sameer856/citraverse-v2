#!/usr/bin/env python3
"""Build evidence-backed PDF and an inline-data Canvas source; no live mutations."""
import datetime as dt,json,pathlib,html
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Preformatted
from reportlab.graphics.shapes import Drawing,Rect,Circle,Line,String
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125';PDF=ROOT/'output/pdf';PDF.mkdir(parents=True,exist_ok=True)
read=lambda name,default:json.loads((OUT/name).read_text()) if (OUT/name).exists() else default
segments=[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))]
manifest=read('manifest.json',{});summary=read('profile-summary.json',{});replay=read('replay-analysis.json',{});comparison=read('comparison.json',{});completion=read('complete.json',{});recommendation=read('recommendation.json',{})
finished=bool(completion);title='Citraverse overnight radar report';now=dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30))).isoformat(timespec='minutes')
styles=getSampleStyleSheet();styles.add(ParagraphStyle('BodyCustom',fontName='Helvetica',fontSize=10.5,leading=15,spaceAfter=9));styles.add(ParagraphStyle('SmallCustom',fontName='Helvetica',fontSize=8.5,leading=12,spaceAfter=7));styles['Title'].fontSize=23;styles['Title'].leading=28
story=[]
def para(text,style='BodyCustom'):story.append(Paragraph(html.escape(text),styles[style]))
def h(text):story.append(Spacer(1,12));story.append(Paragraph(html.escape(text),styles['Heading2']))
def table(headers,rows,widths=None):
 content=[[Paragraph(html.escape(str(c)),styles['SmallCustom']) for c in row] for row in [headers,*rows]]
 t=Table(content,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5ece6')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,colors.HexColor('#8b9a8d')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#d7ded7')),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story.append(t)
def percent(v):return f'{100*v:.1f}%'
def commands(p):return '\n'.join([f"mmwc freq {p['frequency']}",f"mmwc range {p['range_mm']} {p['resolution_mm']}",f"mmwc veloc {p['speed_mm_s']} {p['speed_step_mm_s']}",f"mmwc frame {p['frame_ms']} 0",f"mmwc cfar {p['static_rm']} {p['cfar_value']}"+(f" {p['cfar_method']}" if p['cfar_method']>=0 else ''),f"mmwc clutter_rm {p['clutter_rm']}"])
para(title,'Title');para(('FINAL CAPTURE REVIEW' if finished else 'DRAFT - OVERNIGHT CAPTURE STILL RUNNING')+' | generated '+now,'SmallCustom')
frames=sum(s['counts'].get('fresh',0) for s in segments);minutes=sum(s['duration_s'] for s in segments)/60
para(f'{len(segments)} completed capture windows; {minutes:.1f} recorded minutes; {frames:,} fresh processed-point frames. In-progress windows are excluded from the figures below.')
h('Decision')
para(recommendation.get('conclusion','No final profile has been selected yet. Screening and repeated observations are still in progress. Early scores are only bed-return stability proxies.'))
if recommendation.get('profile'):story.append(Preformatted(commands(recommendation['profile']),styles['Code']))
para('Two people remaining in bed is the user-supplied test condition. No synchronized independent labels, empty-bed control, or one-person control were collected. Exactly two spatial clusters is not verified two-person detection accuracy.')
h('Setup and assumptions')
para('Room: 3 x 3 x 3 m. Sensor: far-left corner, 0.15 m inset from each wall, 2 m above floor, antenna vertically into room, 180 degree upside-down roll, 10 degree down tilt, 135 degree heading toward the centre. These values are transcribed from the supplied screenshots; no physical remounting was performed.')
para('Bed: far-right corner toward near-right. Exact dimensions were not confirmed. Initial footprint uses the dashboard default of 1 x 2 m, mattress height 0.55 m and 0.15 m wall gap. Replay also checks wider bed assumptions. These are analysis assumptions, not newly measured dimensions.')
d=Drawing(440,175);d.add(Rect(18,15,150,150,strokeColor=colors.HexColor('#526857'),fillColor=colors.HexColor('#f3f6f2')));d.add(Rect(110.5,57.5,50,100,strokeColor=colors.HexColor('#5f7562'),fillColor=colors.HexColor('#d7e3d6')));d.add(Circle(25.5,157.5,4,fillColor=colors.HexColor('#274a32')));d.add(Line(25.5,157.5,58,125,strokeColor=colors.HexColor('#274a32'),strokeWidth=2));d.add(String(185,145,'Far-left sensor; diagonal heading',fontSize=10));d.add(String(185,120,'Bed footprint shown at assumed size',fontSize=10));d.add(String(185,95,'Far wall at top; near wall at bottom',fontSize=10));d.add(String(185,70,'X lateral, Y near-to-far, Z up',fontSize=10));story.append(d)
h('Acquisition and comparison method')
para('Authenticated GCP RPC applies a temporary complete radar profile, logs radar read-back replies, verifies fresh frames, then allows 10 seconds settling. Initial screening windows are 8 minutes; a shortlist receives repeated 20-minute windows. Original mode, SPI transport, Cartesian point format and Doppler FFT remain unchanged. No firmware flashing, startup-profile save, or occupied-room noise calibration is performed.')
para('The local archive retains processed Cartesian radar points in RDR2 packets, not raw ADC samples. Metrics use fresh frames with relay age at most 350 ms. Relay age excludes browser transit. Offline spatial replay samples one frame per receive-second and tests horizontal connected-component radii 0.2-0.65 m with 3 or 6 supporting points. The existing room algorithm uses 3D radius 0.65 m and 6 points.')
para('Screening proxy: 40% bed-return persistence, 20% both bed-half support, 20% low outside-bed point fraction, 20% fresh-rate reliability. This is not a calibrated detection-accuracy score. Static furniture can increase persistence. Profile order and natural movement introduce time confounding; repeated windows and baseline repeats help expose it.')
story.append(PageBreak());h('Profile-level results')
rows=[]
for i,p in enumerate(summary.get('profiles',[]),1):rows.append([f"{i}. {p['labels'][0]}",f"{p['duration_minutes']:.1f}",f"{p['fresh_fps']:.2f}",percent(p['bed_presence_fraction']),percent(p['both_halves_fraction']),percent(p['outside_point_fraction']),str(p['age_p95_segment_max'])])
table(['Profile','Min','Fresh FPS','Bed support','Both halves','Outside points','P95 age ms'],rows,[130,36,49,58,58,64,54])
para('Bed support = at least three points in the assumed expanded bed volume. Both halves = at least three points on each side of that footprint. Outside points = fraction of room points outside the bed volume. None of these alone establishes human presence or a correct count.','SmallCustom')
h('Spatial separation replay')
replays={r['segment']:r for r in replay.get('segments',[])};rows=[]
for s in segments:
 r=replays.get(s['segment'],{});f=r.get('cluster_fractions',{});rows.append([s['label'],r.get('sampled_seconds',0),percent(f.get('room3d-two',0)),percent(f.get('r0.3-min6-two',0)),percent(f.get('r0.4-min3-two',0)),percent(f.get('r0.4-min3-many',0))])
table(['Window','Samples','Room 3D: 2','Bed .3/6: 2','Bed .4/3: 2','Bed .4/3: >2'],rows,[154,45,61,63,63,63])
para('Column labels show radius/minimum support. Compare merging (one cluster), apparent separation (two), and fragmentation (more than two). A changed clustering algorithm can improve numerical separation while still grouping reflections incorrectly.','SmallCustom')
h('Failures and recovery')
failures=comparison.get('failures',[])
if failures:
 for f in failures:para(f"{f['label']}: {f['error']}")
else:para('No rejected profile is recorded in completed comparison metadata so far. In-progress operations are not represented by that statement.')
para('Capture-complete marker: '+('present' if finished else 'not present')+'. Original-profile restoration: '+str(completion.get('baseline_restored','not yet due / not verified'))+'.')
h('What the results cannot establish')
for text in ['A validated two-person count, sleeping state, breathing or vital signs.','False-positive rate without an empty-bed test; false-negative rate without synchronized annotations.','Full body height while lying down; observed point height is posture-dependent.','Performance in another room, mounting, bedding arrangement or body position.','Fall-detection performance: the current fall prototype is single-person, and no deliberate fall trial was performed.']:para(text)
h('Reproducibility and rollback')
para('Evidence folder: output/radar_overnight_20261125. baseline.json preserves the original active and saved profiles. events.jsonl records all requested profiles and complete command replies. Each completed segment has a JSON summary, compressed processed-point packet archive and per-frame metric archive. replay-analysis.json and profile-summary.json contain independent offline results. No access keys are included in this report.')
para('Source: Sameer856/citraverse-v2, branch codex/radar-dashboard-room, tools/radar_overnight. Dashboard rollback milestones: dashboard-v1.0.0 (before bed), dashboard-v1.1.0 (bed layout). Restore source with a new revert commit and redeploy; checking out a Git tag alone does not change the live Site.')
def footer(c,doc):
 c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#526857'));c.drawString(42,25,'Citraverse | Overnight field experiment | 25-26 November 2026');c.drawRightString(A4[0]-42,25,str(doc.page))
path=PDF/('citraverse-overnight-radar-report.pdf' if finished else 'citraverse-overnight-radar-DRAFT.pdf')
SimpleDocTemplate(str(path),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=42,title=title).build(story,onFirstPage=footer,onLaterPages=footer)
# All data stays inline; the Canvas performs no fetches and contains no credentials.
data={'finished':finished,'generated':now,'manifest':manifest,'summary':summary,'segments':segments,'replay':replay,'recommendation':recommendation,'completion':completion}
# Omit device health and long transcript objects from the visual payload.
for s in data['segments']:s.pop('health_before',None);s.pop('health_after',None)
canvas='''import {Stack,H1,H2,Text,Grid,Stat,Table,Divider,Select,useCanvasState,useHostTheme} from 'cursor/canvas';
const data:any=__DATA__;
const pct=(v:number)=>`${(100*v).toFixed(1)}%`;
export default function RadarOvernight(){const {tokens:t}=useHostTheme();const [radius,setRadius]=useCanvasState('radar-radius','r0.4-min3');const rows=data.summary.profiles||[];const replay=new Map(data.replay.segments.map((s:any)=>[s.segment,s]));return <Stack gap={20}><H1>Citraverse overnight radar experiment</H1><Text tone="secondary">{data.finished?'Capture complete':'DRAFT — capture still running'} · {data.generated}</Text><Text>{data.recommendation.conclusion||'No final recommendation yet. Compare the completed windows below.'}</Text><Grid columns={3} gap={16}><Stat label="Completed windows" value={String(data.segments.length)}/><Stat label="Recorded minutes" value={(data.segments.reduce((n:number,s:any)=>n+s.duration_s,0)/60).toFixed(1)}/><Stat label="Fresh frames" value={data.segments.reduce((n:number,s:any)=>n+(s.counts.fresh||0),0).toLocaleString()}/></Grid><Text tone="secondary">User reports two people remain in bed. Two clusters are a spatial proxy, not verified person-count accuracy. Exact bed dimensions remain unconfirmed.</Text><Divider/><H2>Profile comparison</H2><Table headers={['Profile','Minutes','Fresh FPS','Bed support','Both halves','Outside points','Max segment P95 age']} rows={rows.map((p:any)=>[p.labels[0],p.duration_minutes.toFixed(1),p.fresh_fps.toFixed(2),pct(p.bed_presence_fraction),pct(p.both_halves_fraction),pct(p.outside_point_fraction),`${p.age_p95_segment_max} ms`])}/><H2>Bed-zone spatial separation</H2><Select value={radius} onChange={setRadius} options={['r0.2-min3','r0.2-min6','r0.3-min3','r0.3-min6','r0.4-min3','r0.4-min6','r0.5-min3','r0.5-min6','r0.65-min3','r0.65-min6'].map(v=>({value:v,label:v.replace('r','Radius ').replace('-min',' m / minimum ')+' points'}))}/><Table headers={['Window','Samples','Room 3D: 2 clusters','Bed: 1','Bed: 2','Bed: >2']} rows={data.segments.map((s:any)=>{const r:any=replay.get(s.segment);const f=r?.cluster_fractions||{};return [s.label,r?.sampled_seconds||0,pct(f['room3d-two']||0),pct(f[radius+'-one']||0),pct(f[radius+'-two']||0),pct(f[radius+'-many']||0)]})}/><Text tone="secondary">Horizontal bed clustering avoids splitting a body by height; smaller radii may fragment it. Neither method recognizes identity. The replay samples one fresh frame per receive-second.</Text><Divider/><H2>Recorded setup</H2><Text>3 × 3 × 3 m room; sensor at far-left, height 2 m, 180° roll, 10° down tilt, 135° heading. Bed at far-right toward near-right; initial assumed size 1 × 2 m, 0.55 m high, 0.15 m wall gap.</Text><H2>Evidence and limits</H2><Text>Every temporary profile is checked against the radar's reply and fresh frames. No firmware flash, occupied-room noise calibration or NVS save is part of this experiment. Original startup settings remain recoverable.</Text><Text>Without empty-bed and one-person controls, persistent furniture returns cannot be distinguished conclusively from sleepers. Full standing height, breathing, sleep state and fall accuracy are outside this test.</Text><Text tone="secondary">Local evidence: output/radar_overnight_20261125. GitHub: Sameer856/citraverse-v2 → codex/radar-dashboard-room → tools/radar_overnight.</Text></Stack>}
'''.replace('__DATA__',json.dumps(data,separators=(',',':')))
(OUT/'morning-report-canvas.txt').write_text(canvas)
print(path)
