"""
dashboard/pages/10_digital_twin.py  -  AuroLab OT-2 Digital Twin
Full 3D robot simulation. No GPU required.
"""

import json
import streamlit as st
import httpx

st.set_page_config(page_title="Digital Twin - AuroLab", page_icon="!", layout="wide")

API_BASE = "http://localhost:8080"

def api_get(path):
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=4.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

history    = st.session_state.get("protocol_history", [])
live_steps = history[0].get("steps", []) if history else []
lab_state  = api_get("/api/v1/vision/current") or {}
labware    = lab_state.get("labware_map", {}) or {
    "1":"96_well_plate","2":"96_well_plate","3":"plate_reader_slot",
    "5":"tube_rack","7":"incubator_slot","11":"tip_rack_300ul","12":"waste_container",
}

SLOT_XZ = {
    "1":[14.4,10.0],"2":[132.5,10.0],"3":[250.6,10.0],
    "4":[14.4,75.1],"5":[132.5,75.1],"6":[250.6,75.1],
    "7":[14.4,140.2],"8":[132.5,140.2],"9":[250.6,140.2],
    "10":[14.4,205.3],"11":[132.5,205.3],"12":[250.6,205.3],
}
LH = {"96_well_plate":14.5,"384_well_plate":14.5,"tip_rack_300ul":65.0,"tip_rack_200ul":65.0,
      "tip_rack_10ul":60.0,"tip_rack_1000ul":95.0,"tube_rack":45.0,"tube_rack_1.5ml":45.0,
      "waste_container":50.0,"plate_reader_slot":80.0,"incubator_slot":100.0,
      "reservoir_12_well":30.0,"generic":30.0}
LC = {"96_well_plate":"#1a5fb4","384_well_plate":"#1a5fb4","tip_rack_300ul":"#e5a50a",
      "tip_rack_200ul":"#e5a50a","tip_rack_10ul":"#c88800","tip_rack_1000ul":"#d4a000",
      "tube_rack":"#9141ac","tube_rack_1.5ml":"#9141ac","waste_container":"#5c5c5c",
      "plate_reader_slot":"#26a269","incubator_slot":"#c64600","generic":"#7c7c7c"}

lw_js = []
for slot, ltype in labware.items():
    pos = SLOT_XZ.get(str(slot))
    if not pos: continue
    lw_js.append({"slot":str(slot),"type":ltype,"x":pos[0]+58.5,"z":pos[1]+58.5,
                  "h":LH.get(ltype,30.0),"color":LC.get(ltype,"#7c7c7c")})

DEMO = [
    {"type":"home","label":"Home - initialise","slot":None},
    {"type":"pick_up_tip","label":"Pick up tip - slot 11","slot":11},
    {"type":"aspirate","label":"Aspirate 50 uL - slot 1","slot":1,"vol":50},
    {"type":"dispense","label":"Dispense 50 uL - slot 2","slot":2,"vol":50},
    {"type":"mix","label":"Mix 5x - slot 2","slot":2},
    {"type":"drop_tip","label":"Eject tip - slot 12","slot":12},
    {"type":"pick_up_tip","label":"Pick up tip - slot 11","slot":11},
    {"type":"aspirate","label":"Aspirate 25 uL - slot 1","slot":1,"vol":25},
    {"type":"dispense","label":"Dispense 25 uL - slot 2","slot":2,"vol":25},
    {"type":"drop_tip","label":"Eject tip - slot 12","slot":12},
    {"type":"centrifuge","label":"Centrifuge 3000 rpm 5 min","slot":None},
    {"type":"incubate","label":"Incubate 37C 30 min slot 7","slot":7},
    {"type":"read_absorbance","label":"Read absorbance 562 nm slot 3","slot":3},
    {"type":"home","label":"Home - protocol complete","slot":None},
]

if live_steps:
    import re
    def _s(inst, d=None):
        m = re.search(r"slot\s*(\d+)", inst, re.I)
        return int(m.group(1)) if m else d
    cmds = [{"type":"home","label":"Home - start","slot":None}]
    for s in live_steps:
        inst = s.get("instruction","").lower()
        lbl  = s["instruction"][:60]
        if any(k in inst for k in ["pipette","aspirate","transfer","add"]):
            cmds.append({"type":"aspirate","label":lbl,"slot":_s(inst,1),"vol":50})
        elif "dispense" in inst:
            cmds.append({"type":"dispense","label":lbl,"slot":_s(inst,2),"vol":50})
        elif "centrifuge" in inst or "spin" in inst:
            cmds.append({"type":"centrifuge","label":lbl,"slot":None})
        elif "incubate" in inst or "warm" in inst:
            cmds.append({"type":"incubate","label":lbl,"slot":_s(inst,7)})
        elif "read" in inst or "absorbance" in inst:
            cmds.append({"type":"read_absorbance","label":lbl,"slot":_s(inst,3)})
        elif "mix" in inst or "vortex" in inst:
            cmds.append({"type":"mix","label":lbl,"slot":_s(inst,2)})
        elif "shake" in inst:
            cmds.append({"type":"shake","label":lbl,"slot":_s(inst,5)})
        else:
            cmds.append({"type":"pause","label":lbl,"slot":None})
    cmds.append({"type":"home","label":"Home - complete","slot":None})
    sim_cmds = cmds if len(cmds) > 2 else DEMO
else:
    sim_cmds = DEMO

cmds_j = json.dumps(sim_cmds)
lw_j   = json.dumps(lw_js)
sp_j   = json.dumps({k:[v[0]+58.5,v[1]+58.5] for k,v in SLOT_XZ.items()})

st.markdown("## Digital Twin - OT-2 Live Simulation")
st.markdown("3D robot simulation - Drag to orbit - Scroll to zoom - Press Play to run")

HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0c0c10;font-family:'IBM Plex Mono',monospace;overflow:hidden;color:#c8c8d0}
#app{display:flex;width:100vw;height:100vh}
#sb{width:280px;flex-shrink:0;background:#0f0f14;border-right:1px solid #1e1e28;display:flex;flex-direction:column}
#hdr{padding:12px 14px;border-bottom:1px solid #1e1e28}
#hdr h1{font-size:12px;font-weight:500;color:#a78bfa;letter-spacing:.05em}
#hdr p{font-size:9px;color:#444458;margin-top:2px}
#sp{padding:10px 14px;border-bottom:1px solid #1e1e28}
#sl{font-size:10px;color:#c8c8d0;min-height:30px;line-height:1.5}
#st{font-size:8px;color:#7c6af7;letter-spacing:.1em;margin-top:3px;text-transform:uppercase}
#pb{height:2px;background:#1e1e28;margin-top:6px;border-radius:1px}
#pf{height:100%;background:#7c6af7;border-radius:1px;transition:width .3s;width:0}
#ctl{padding:8px 14px;border-bottom:1px solid #1e1e28;display:flex;gap:5px;align-items:center;flex-wrap:wrap}
.btn{background:#1a1a24;border:1px solid #2a2a38;color:#c8c8d0;font-size:10px;padding:4px 9px;border-radius:3px;cursor:pointer;transition:all .15s}
.btn:hover{background:#252533;border-color:#7c6af7;color:#a78bfa}
.btn.on{background:#2a1f4a;border-color:#7c6af7;color:#a78bfa}
#sv{font-size:9px;color:#a78bfa;min-width:26px}
#log{flex:1;overflow-y:auto;padding:6px 0}
#log::-webkit-scrollbar{width:2px}
#log::-webkit-scrollbar-thumb{background:#222230}
.le{padding:4px 14px;font-size:9px;border-left:2px solid transparent;cursor:pointer}
.le.on{background:#1a1428;border-color:#7c6af7;color:#c8c8d0}
.le.done{color:#333345;border-color:#1e1e28}
.le.pend{color:#222235}
.sn{color:#333345;margin-right:5px}
.lt{font-size:7px;display:inline-block;padding:1px 4px;border-radius:2px;margin-right:4px;vertical-align:middle}
.t-home{background:#1a1a24;color:#555568}
.t-pick_up_tip{background:#1e2a0a;color:#86c232}
.t-drop_tip{background:#2a1e0a;color:#ffb74d}
.t-aspirate{background:#0a1e2a;color:#4fc3f7}
.t-dispense{background:#0a2a1e;color:#4db6ac}
.t-mix{background:#1e1a2a;color:#b39ddb}
.t-centrifuge{background:#2a0a1a;color:#ef9a9a}
.t-incubate{background:#1e2a0a;color:#aed581}
.t-read_absorbance{background:#0a1a2a;color:#80deea}
.t-shake{background:#2a1e0a;color:#ffe082}
.t-pause{background:#1e1e1e;color:#666680}
#cw{flex:1;position:relative}
canvas{display:block;width:100%;height:100%}
#cf{position:absolute;inset:0;background:rgba(220,50,50,0);pointer-events:none;transition:background .25s}
#info{position:absolute;top:10px;right:10px;font-size:9px;color:#222235;text-align:right;pointer-events:none;line-height:2}
#stats{position:absolute;bottom:10px;right:10px;font-size:9px;color:#333345;text-align:right;line-height:1.8}
</style></head><body>
<div id="app">
<div id="sb">
  <div id="hdr"><h1>AuroLab Digital Twin</h1><p>OT-2 Three.js simulation</p></div>
  <div id="sp">
    <div id="sl">Ready - press Play</div>
    <div id="st">-</div>
    <div id="pb"><div id="pf"></div></div>
  </div>
  <div id="ctl">
    <button class="btn" onclick="prev()">&#9664;</button>
    <button class="btn on" id="pb2" onclick="playPause()">&#9654; Play</button>
    <button class="btn" onclick="nxt()">&#9654;</button>
    <button class="btn" onclick="rst()">&#10227;</button>
    <input type="range" min="1" max="8" value="3" id="spsl" style="width:50px" oninput="setSp(this.value)">
    <span id="sv">1x</span>
  </div>
  <div id="log"></div>
</div>
<div id="cw">
  <canvas id="c"></canvas>
  <div id="cf"></div>
  <div id="info"><span>Drag orbit</span><span>Scroll zoom</span></div>
  <div id="stats">
    <span id="s1">Commands: 0</span>
    <span id="s2">Volume: 0 uL</span>
    <span id="s3">Tips: 0</span>
  </div>
</div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const CMDS=__CMDS__;
const LW=__LW__;
const SP=__SP__;
const SPDS=[.25,.5,1,2,3,4,6,8];
let si=2,vol=0,tips=0,fr=0,playing=false,idx=-1,tmr=null;
function setSp(v){si=parseInt(v)-1;document.getElementById('sv').textContent=SPDS[si]+'x';}
const wrap=document.getElementById('cw'),cv=document.getElementById('c');
const W=()=>wrap.clientWidth,H=()=>wrap.clientHeight;
const rnd=new THREE.WebGLRenderer({canvas:cv,antialias:true});
rnd.setPixelRatio(devicePixelRatio);rnd.setSize(W(),H());
rnd.shadowMap.enabled=true;rnd.setClearColor(0x0c0c10);
const sc=new THREE.Scene();sc.fog=new THREE.Fog(0x0c0c10,800,1600);
const cam=new THREE.PerspectiveCamera(42,W()/H(),1,2000);
sc.add(new THREE.AmbientLight(0x304050,.7));
const sun=new THREE.DirectionalLight(0xffffff,1.1);
sun.position.set(300,500,200);sun.castShadow=true;
sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-400;sun.shadow.camera.right=400;
sun.shadow.camera.top=400;sun.shadow.camera.bottom=-400;sun.shadow.camera.far=1500;sc.add(sun);
sc.add(Object.assign(new THREE.DirectionalLight(0x4466aa,.35),{position:new THREE.Vector3(-200,200,-300)}));
sc.add(Object.assign(new THREE.DirectionalLight(0x7c6af7,.2),{position:new THREE.Vector3(0,50,400)}));
const L=(a,b,t)=>a+(b-a)*t;
function bx(w,h,d,col,sh=30,a=1){
  const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),
    new THREE.MeshPhongMaterial({color:col,shininess:sh,transparent:a<1,opacity:a}));
  m.castShadow=m.receiveShadow=true;return m;}
function cy(rt,rb,h,seg,col,sh=60){
  const m=new THREE.Mesh(new THREE.CylinderGeometry(rt,rb,h,seg),
    new THREE.MeshPhongMaterial({color:col,shininess:sh}));m.castShadow=true;return m;}
// Deck
const dk=bx(400,10,300,0x1a1a2a,5);dk.position.set(196,-5,140);sc.add(dk);
const rM=new THREE.MeshPhongMaterial({color:0x252535,shininess:20});
[[400,6,6,196,0,-3],[400,6,6,196,0,283],[6,6,300,-3,0,140],[6,6,300,395,0,140]].forEach(([w,h,d,x,y,z])=>{
  const r=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),rM);r.position.set(x,y,z);sc.add(r);});
const dM=new THREE.MeshPhongMaterial({color:0x1e1e2e,shininess:5});
for(let c=1;c<=3;c++){const d=new THREE.Mesh(new THREE.BoxGeometry(2,14,290),dM);d.position.set(c*118-5,7,140);sc.add(d);}
for(let r=1;r<=3;r++){const d=new THREE.Mesh(new THREE.BoxGeometry(390,14,2),dM);d.position.set(196,7,r*65.1);sc.add(d);}
// Labels
function lbl(t,x,z){
  const cv2=document.createElement('canvas');cv2.width=96;cv2.height=48;
  const ctx=cv2.getContext('2d');ctx.fillStyle='#1e2a3a';ctx.font='bold 22px monospace';
  ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(t,48,24);
  const pl=new THREE.Mesh(new THREE.PlaneGeometry(36,18),
    new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(cv2),transparent:true,opacity:.5}));
  pl.rotation.x=-Math.PI/2;pl.position.set(x,.6,z);sc.add(pl);}
[[1,14.4,10],[2,132.5,10],[3,250.6,10],[4,14.4,75.1],[5,132.5,75.1],[6,250.6,75.1],
 [7,14.4,140.2],[8,132.5,140.2],[9,250.6,140.2],[10,14.4,205.3],[11,132.5,205.3],[12,250.6,205.3]]
  .forEach(([n,sx,sz])=>lbl(String(n),sx+58.5,sz+58.5));
// Labware
const lwM={};
LW.forEach(item=>{
  const col=parseInt(item.color.replace('#',''),16);
  const b=bx(114,item.h,114,col,60,.88);b.position.set(item.x,item.h/2,item.z);sc.add(b);
  const wf=new THREE.LineSegments(new THREE.EdgesGeometry(b.geometry),
    new THREE.LineBasicMaterial({color:col,transparent:true,opacity:.3}));
  wf.position.copy(b.position);sc.add(wf);
  lwM[item.slot]={m:b,col,ox:item.x,oy:item.h/2,oz:item.z};});
// Gantry X-rail
const xr=bx(420,12,12,0x888898,90);xr.position.set(196,230,140);sc.add(xr);
const pM2=new THREE.MeshPhongMaterial({color:0x666680,shininess:70});
[-8,288].forEach(z=>{
  const p=new THREE.Mesh(new THREE.BoxGeometry(12,250,12),pM2);p.position.set(196,115,z);p.castShadow=true;sc.add(p);
  const f=new THREE.Mesh(new THREE.BoxGeometry(24,12,24),pM2);f.position.set(196,-6,z);sc.add(f);});
// Arm
const arm=new THREE.Group();
arm.add(Object.assign(bx(30,22,30,0x555568,80),{position:new THREE.Vector3(0,0,0)}));
const pipB=cy(5,5,80,12,0x444458,60);pipB.position.set(0,-46,0);arm.add(pipB);
const nz=cy(3,1.5,20,10,0x333345,40);nz.position.set(0,-92,0);arm.add(nz);
const tip=cy(2.5,.8,32,8,0xd4a000,100);tip.position.set(0,-112,0);tip.visible=false;arm.add(tip);
const plg=cy(1.5,1.5,60,8,0x7c6af7,80);plg.position.set(0,-10,0);arm.add(plg);
arm.position.set(196,226,140);sc.add(arm);
// Scan beam
let beam=null;
function showBeam(x,z){
  if(beam){sc.remove(beam);beam=null;}
  beam=new THREE.Mesh(new THREE.BoxGeometry(2,80,2),
    new THREE.MeshPhongMaterial({color:0x80deea,transparent:true,opacity:.7,emissive:0x006070,emissiveIntensity:.5}));
  beam.position.set(x,40,z);sc.add(beam);
  setTimeout(()=>{if(beam){sc.remove(beam);beam=null;}},1200/SPDS[si]);}
// Particles
const pts=[],pG=new THREE.SphereGeometry(1.5,6,6);
const pM={a:new THREE.MeshPhongMaterial({color:0x4fc3f7,transparent:true,opacity:.85}),
          d:new THREE.MeshPhongMaterial({color:0x4db6ac,transparent:true,opacity:.85}),
          m:new THREE.MeshPhongMaterial({color:0xb39ddb,transparent:true,opacity:.8})};
function spwn(x,z,t,n=12){
  for(let i=0;i<n;i++){
    const p=new THREE.Mesh(pG,pM[t]||pM.d);
    const a=Math.random()*Math.PI*2,s=.4+Math.random()*.8;
    p.position.set(x,60,z);p._vx=Math.sin(a)*s*.3;p._vy=1.5+Math.random()*2;
    p._vz=Math.cos(a)*s*.3;p._l=1;sc.add(p);pts.push(p);}}
function tickPts(){
  for(let i=pts.length-1;i>=0;i--){
    const p=pts[i];p._vy-=.12;p.position.x+=p._vx;p.position.y+=p._vy;p.position.z+=p._vz;
    p._l-=.025;p.material.opacity=Math.max(0,p._l*.85);p.scale.setScalar(Math.max(.1,p._l));
    if(p._l<=0||p.position.y<0){sc.remove(p);pts.splice(i,1);}}}
let ax=196,ay=226,az=140,cx2=196,cy3=226,cz2=140;
let plgT=-10,plgC=-10,spnA=0,spinning=false;
let glSl=null,glV=0,glD=1;
function slCtr(slot){const p=SP[String(slot)];return p?{x:p[0],z:p[1]}:{x:196,z:140};}
const DUR={home:1200,pick_up_tip:1400,drop_tip:1000,aspirate:1600,dispense:1400,
           mix:2000,centrifuge:3000,incubate:2500,shake:2000,read_absorbance:1800,pause:800};
function exec(i){
  if(i<0||i>=CMDS.length)return;
  const cmd=CMDS[i];idx=i;updLog(i);updPrg(i);
  document.getElementById('sl').textContent=cmd.label||cmd.type;
  document.getElementById('st').textContent=cmd.type.replace(/_/g,' ').toUpperCase();
  const slc=cmd.slot?slCtr(cmd.slot):{x:196,z:140};
  ax=cmd.type==='home'?196:slc.x;az=cmd.type==='home'?140:slc.z;ay=226;
  if(cmd.type==='pick_up_tip'){tip.visible=true;tip.material.color.setHex(0xd4a000);tips++;document.getElementById('s3').textContent='Tips: '+tips;}
  if(cmd.type==='drop_tip'){setTimeout(()=>{tip.visible=false;},400/SPDS[si]);spwn(slc.x,slc.z,'d',6);}
  if(cmd.type==='aspirate'){plgT=-30;setTimeout(()=>{plgT=-10;},600/SPDS[si]);spwn(slc.x,slc.z,'a',14);vol+=(cmd.vol||50);document.getElementById('s2').textContent='Volume: '+vol.toFixed(0)+' uL';}
  if(cmd.type==='dispense'){plgT=10;setTimeout(()=>{plgT=-10;},600/SPDS[si]);spwn(slc.x,slc.z,'d',14);}
  if(cmd.type==='mix'){[0,300,600,900].forEach(t=>setTimeout(()=>spwn(slc.x,slc.z,'m',8),t/SPDS[si]));}
  if(cmd.type==='centrifuge'){spinning=true;setTimeout(()=>spinning=false,3000/SPDS[si]);}
  if(cmd.type==='incubate'&&cmd.slot){
    glSl=String(cmd.slot);glV=0;
    setTimeout(()=>{glSl=null;const lw=lwM[String(cmd.slot)];if(lw)lw.m.material.color.setHex(lw.col);},2500/SPDS[si]);}
  if(cmd.type==='read_absorbance'||cmd.type==='read_fluorescence'){setTimeout(()=>showBeam(slc.x,slc.z),500/SPDS[si]);}
  if(cmd.type==='shake'&&cmd.slot){
    const lw=lwM[String(cmd.slot)];if(lw){let t=0;const iv=setInterval(()=>{
      lw.m.position.x=lw.ox+(Math.random()-.5)*3;if(++t>20){clearInterval(iv);lw.m.position.x=lw.ox;}},70);}}
  const dur=(DUR[cmd.type]||1200)/SPDS[si];
  if(playing){tmr=setTimeout(()=>{if(i+1<CMDS.length)exec(i+1);else{playing=false;setBtn(false);}},dur);}}
function setBtn(on){const b=document.getElementById('pb2');b.textContent=on?'&#9646;&#9646; Pause':'&#9654; Play';b.className='btn '+(on?'on':'');}
function playPause(){
  playing=!playing;setBtn(playing);
  if(playing){if(tmr)clearTimeout(tmr);if(idx>=CMDS.length-1)idx=-1;exec(idx+1);}
  else{if(tmr)clearTimeout(tmr);}}
function nxt(){if(tmr)clearTimeout(tmr);playing=false;setBtn(false);exec(Math.min(idx+1,CMDS.length-1));}
function prev(){if(tmr)clearTimeout(tmr);playing=false;setBtn(false);exec(Math.max(idx-1,0));}
function rst(){
  if(tmr)clearTimeout(tmr);playing=false;idx=-1;vol=0;tips=0;
  ax=196;ay=226;az=140;tip.visible=false;setBtn(false);
  document.getElementById('sl').textContent='Ready - press Play';
  document.getElementById('st').textContent='-';
  document.getElementById('pf').style.width='0%';
  document.getElementById('s1').textContent='Commands: 0';
  document.getElementById('s2').textContent='Volume: 0 uL';
  document.getElementById('s3').textContent='Tips: 0';
  buildLog();}
function buildLog(){
  const log=document.getElementById('log');log.innerHTML='';
  CMDS.forEach((cmd,i)=>{
    const d=document.createElement('div');d.className='le pend';d.id='le'+i;
    d.onclick=()=>{if(tmr)clearTimeout(tmr);playing=false;setBtn(false);exec(i);};
    d.innerHTML='<span class="sn">'+String(i+1).padStart(2,'0')+'</span><span class="lt t-'+cmd.type+'">'+cmd.type+'</span>'+(cmd.label||cmd.type);
    log.appendChild(d);});}
function updLog(i){
  CMDS.forEach((_,j)=>{const e=document.getElementById('le'+j);if(e)e.className='le '+(j<i?'done':j===i?'on':'pend');});
  const e=document.getElementById('le'+i);if(e)e.scrollIntoView({behavior:'smooth',block:'nearest'});}
function updPrg(i){
  document.getElementById('pf').style.width=(CMDS.length>1?(i/(CMDS.length-1)*100):0).toFixed(1)+'%';
  document.getElementById('s1').textContent='Commands: '+(i+1)+'/'+CMDS.length;}
// Camera orbit
let th=.4,ph=.75,cr=520,drag=false,pmx=0,pmy=0;
const ct=new THREE.Vector3(196,60,140);
function apCam(){cam.position.set(ct.x+cr*Math.sin(ph)*Math.sin(th),ct.y+cr*Math.cos(ph),ct.z+cr*Math.sin(ph)*Math.cos(th));cam.lookAt(ct);}
apCam();
cv.addEventListener('mousedown',e=>{drag=true;pmx=e.clientX;pmy=e.clientY;});
window.addEventListener('mouseup',()=>drag=false);
window.addEventListener('mousemove',e=>{
  if(!drag)return;th-=(e.clientX-pmx)*.006;ph=Math.max(.05,Math.min(1.4,ph-(e.clientY-pmy)*.005));
  pmx=e.clientX;pmy=e.clientY;apCam();});
cv.addEventListener('wheel',e=>{cr=Math.max(150,Math.min(900,cr+e.deltaY*.35));apCam();e.preventDefault();},{passive:false});
// Render loop
function animate(){
  requestAnimationFrame(animate);fr++;
  const s=SPDS[si];
  cx2=L(cx2,ax,.06);cy3=L(cy3,ay,.06);cz2=L(cz2,az,.06);arm.position.set(cx2,cy3,cz2);
  plgC=L(plgC,plgT,.1);plg.position.y=L(plg.position.y,plgC,.12);
  if(spinning){spnA+=.15*s;const lw=lwM['5']||lwM['1'];if(lw)lw.m.rotation.y=spnA;}
  if(glSl){glV+=.04*glD*s;if(glV>1){glV=1;glD=-1;}if(glV<0){glV=0;glD=1;}
    const lw=lwM[glSl];if(lw)lw.m.material.color.setRGB(.3+glV*.7,.1+glV*.15,.05);}
  if(beam)beam.rotation.z=Math.sin(fr*.2)*.05;
  tickPts();
  if(Math.abs(cx2-ax)<2&&Math.abs(cz2-az)<2)arm.position.y+=Math.sin(fr*.015)*.5;
  xr.position.x=L(xr.position.x,cx2,.04);
  rnd.render(sc,cam);}
new ResizeObserver(()=>{rnd.setSize(W(),H());cam.aspect=W()/H();cam.updateProjectionMatrix();}).observe(wrap);
buildLog();animate();
</script></body></html>"""

HTML = HTML.replace("__CMDS__", cmds_j).replace("__LW__", lw_j).replace("__SP__", sp_j)
st.components.v1.html(HTML, height=720, scrolling=False)