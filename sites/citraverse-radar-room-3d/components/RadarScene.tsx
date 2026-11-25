'use client';
import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import type {Bed} from './BedSettings';
import {bedPlacement} from '../lib/radar/bed.mjs';
import {sensorPosition,rotateSensor} from '../lib/radar/mount.mjs';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
export type Point={x:number;y:number;z:number;v:number;snr:number;presence:boolean};
export type PersonBox={id:number;x:number;y:number;top:number;span:number;count:number;bounds:number[]};
export type Mount={schemaVersion:number;face:string;rollDeg:number;positionX:number;positionY:number;corner:string;inset:number;aimAtCenter:boolean;mount:string;height:number;tiltDeg:number;yawDeg:number;range:number;width:number;depth:number;roomHeight:number};
export default function RadarScene({points,people,bed,mount,view,alert}:{bed:Bed;points:Point[];people:PersonBox[];mount:Mount;view:{name:string;n:number};alert:boolean}){
 const host=useRef<HTMLDivElement>(null),live=useRef({points,people,alert}),changeView=useRef<(name:string)=>void>(()=>{});const [error,setError]=useState('');
 useEffect(()=>{live.current={points,people,alert};},[points,people,alert]);
 useEffect(()=>{changeView.current(view.name);},[view]);
 useEffect(()=>{
  const container=host.current;if(!container)return;let renderer:THREE.WebGLRenderer;
  try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}catch{setError('3D rendering is unavailable in this browser. Try a browser with WebGL enabled.');return;}
  setError('');const scene=new THREE.Scene();scene.background=new THREE.Color('#0d211d');
  const camera=new THREE.PerspectiveCamera(45,1,.05,100);renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.appendChild(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.target.set(0,.8,-mount.depth/2);controls.maxDistance=22;controls.minDistance=1.4;controls.maxPolarAngle=Math.PI*.49;
  const fit=(name:string)=>{const d=Math.max(mount.width,mount.depth)*1.25;if(name==='top')camera.position.set(0,d,-mount.depth/2+.01);else if(name==='front')camera.position.set(0,2,d*.9);else camera.position.set(d*.85,d*.72,d*.5);controls.target.set(0,.6,-mount.depth/2);controls.update();};changeView.current=fit;fit('iso');
  const floor=new THREE.Mesh(new THREE.PlaneGeometry(mount.width,mount.depth),new THREE.MeshBasicMaterial({color:'#18382f',side:THREE.DoubleSide}));floor.rotation.x=-Math.PI/2;floor.position.set(0,-.02,-mount.depth/2);scene.add(floor);
  const grid=new THREE.GridHelper(Math.max(mount.width,mount.depth),Math.ceil(Math.max(mount.width,mount.depth)),0x436557,0x294c40);grid.position.z=-mount.depth/2;scene.add(grid);
  const box=new THREE.Box3(new THREE.Vector3(-mount.width/2,0,-mount.depth),new THREE.Vector3(mount.width/2,mount.roomHeight,0));const room=new THREE.Box3Helper(box,0x426154);scene.add(room);
  if(bed.enabled){
   const b=bedPlacement(bed,mount),bedGroup=new THREE.Group();bedGroup.position.set(b.x,0,-b.y);scene.add(bedGroup);
   const part=(w:number,h:number,d:number,x:number,y:number,z:number,color:number)=>{const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshBasicMaterial({color}));mesh.position.set(x,y,z);bedGroup.add(mesh);return mesh;};
   const mattress=Math.min(.18,b.height*.35),frameHeight=Math.max(.08,b.height-mattress-.1);
   part(b.width,frameHeight,b.length,0,.1+frameHeight/2,0,0x6b7862);
   part(b.width-.04,mattress,b.length-.04,0,b.height-mattress/2,0,0xd5ddc6);
   part(b.width*.92,.025,b.length*.65,0,b.height+.012,b.length*.14,0x739a85);
   part(b.width*.68,.07,Math.min(.42,b.length*.2),0,b.height+.035,-b.length*.34,0xeff0de);
   part(b.width,.35,.06,0,b.height+.075,-b.length/2+.03,0x829875);
   const outline=new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(b.x-b.width/2,.01,-b.y-b.length/2),new THREE.Vector3(b.x+b.width/2,b.height,-b.y+b.length/2)),0xa2b297);scene.add(outline);
  }
  const origin=sensorPosition(mount),toThree=(p:{x:number;y:number;z:number})=>new THREE.Vector3(p.x,p.z,-p.y);
  const basis=new THREE.Matrix4().makeBasis(toThree(rotateSensor({x:1,y:0,z:0},mount)),toThree(rotateSensor({x:0,y:1,z:0},mount)),toThree(rotateSensor({x:0,y:0,z:1},mount)));
  const sensor=new THREE.Group();sensor.position.copy(toThree(origin));sensor.quaternion.setFromRotationMatrix(basis);scene.add(sensor);
  sensor.add(new THREE.Mesh(new THREE.BoxGeometry(.18,.04,.28),new THREE.MeshBasicMaterial({color:0xf0e7b5})));
  const marker=new THREE.Mesh(new THREE.SphereGeometry(.025,12,8),new THREE.MeshBasicMaterial({color:0xa5e6ae}));marker.position.set(0,.035,.1);sensor.add(marker);
  scene.add(new THREE.ArrowHelper(toThree(rotateSensor({x:0,y:1,z:0},mount)).normalize(),toThree(origin),.65,0xa5e6ae,.12,.07));
  const positions=new Float32Array(8192*3),colors=new Float32Array(8192*3),geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.BufferAttribute(positions,3));geo.setAttribute('color',new THREE.BufferAttribute(colors,3));geo.setDrawRange(0,0);
  const material=new THREE.PointsMaterial({size:.1,vertexColors:true,sizeAttenuation:true});const cloud=new THREE.Points(geo,material);cloud.frustumCulled=false;scene.add(cloud);
  const warning=new THREE.Color('#ff7f66'),motion=new THREE.Color('#f2c66d'),presence=new THREE.Color('#a5e6ae');
  const boxLayer=document.createElement('div');boxLayer.className='person-label-layer';container.appendChild(boxLayer);
  const boxes=Array.from({length:8},()=>{const helper=new THREE.Box3Helper(new THREE.Box3(),0xa5e6ae);helper.visible=false;scene.add(helper);const label=document.createElement('div');label.className='person-label';label.hidden=true;boxLayer.appendChild(label);return {helper,label};});
  const projected=new THREE.Vector3();
  let raf=0;const resize=()=>{const {width,height}=container.getBoundingClientRect();renderer.setSize(width,height);camera.aspect=width/Math.max(height,1);camera.updateProjectionMatrix();};const observer=new ResizeObserver(resize);observer.observe(container);resize();
  const animate=()=>{let n=0;for(const p of live.current.points){if(n>=8192)break;const color=live.current.alert?warning:p.presence?presence:motion;positions[n*3]=p.x;positions[n*3+1]=p.z;positions[n*3+2]=-p.y;color.toArray(colors,n*3);n++;}geo.setDrawRange(0,n);geo.attributes.position.needsUpdate=true;geo.attributes.color.needsUpdate=true;controls.update();for(let i=0;i<boxes.length;i++){const {helper,label}=boxes[i],p=live.current.people[i];helper.visible=!!p;label.hidden=true;if(!p)continue;const b=p.bounds;helper.box.min.set(b[0]-.06,Math.max(0,b[4]-.04),-b[3]-.06);helper.box.max.set(b[1]+.06,b[5]+.06,-b[2]+.06);(helper.material as THREE.LineBasicMaterial).color.copy(live.current.alert?warning:presence);projected.set(p.x,b[5]+.18,-p.y).project(camera);if(projected.z>=-1&&projected.z<=1&&Math.abs(projected.x)<=1&&Math.abs(projected.y)<=1){label.hidden=false;label.textContent=`P${p.id} · ~${p.top.toFixed(2)} m top`;label.style.left=`${(projected.x+1)*50}%`;label.style.top=`${(1-projected.y)*50}%`;}}
   renderer.render(scene,camera);raf=requestAnimationFrame(animate);};animate();
  return()=>{cancelAnimationFrame(raf);observer.disconnect();controls.dispose();scene.traverse(o=>{if(o instanceof THREE.Mesh||o instanceof THREE.Line||o instanceof THREE.Points){o.geometry.dispose();const m=o.material;if(Array.isArray(m))m.forEach(x=>x.dispose());else m.dispose();}});renderer.dispose();renderer.domElement.remove();boxLayer.remove();changeView.current=()=>{};};
 },[mount,bed]);
 return <div className="scene" ref={host} aria-label="Interactive live 3D radar point cloud">{error&&<div className="scene-error">{error}</div>}</div>;
}
