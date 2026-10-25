/* All camera/control data stays on the LAN. Three.js assets are served locally. */
'use strict';
const $ = id => document.getElementById(id);
let state = {}, scans = [], selected = null, live = true, playing = false, playTimer = null;
let renderer, scene, camera, controls, object, sphere, previousBusy = false, lastScanRefresh = 0;
function message(text, error=false) { $('message').textContent=text; $('message').parentElement.classList.toggle('error',error); }
async function api(path, data) {
  const options=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Scanner-Request':'1'},body:JSON.stringify(data)};
  const response=await fetch(path,options); const result=await response.json();
  if(!response.ok) throw Error(result.error || 'Request failed'); return result;
}
async function action(path,data={}) { try {state=await api(path,data);renderState();await refreshScans();}catch(e){message(e.message,true);} }
function imagesLive() {
  if(!live)return;
  for(const kind of ['rgb','depth']) {const img=$(kind);if(!img.dataset.live){img.src='/api/live/'+kind;img.dataset.live='1';}}
}
function mode(isLive) {
  live=isLive; playing=false;clearTimeout(playTimer);$('play').textContent='Play';
  $('liveMode').classList.toggle('selected',live);$('replayMode').classList.toggle('selected',!live);$('replayBar').classList.toggle('hidden',live);
  for(const id of ['rgb','depth']) {$(id).classList.remove('loaded');delete $(id).dataset.live;$(id).removeAttribute('src');}
  if(live)imagesLive();else replayFrame();
}
function replayFrame() {
  const scan=scans.find(s=>s.id===selected);
  if(live||!scan||!scan.frames)return;
  const index=Math.min(Number($('scrubber').value),scan.frames-1);$('scrubber').max=scan.frames-1;
  for(const kind of ['rgb','depth'])$(kind).src='/api/scans/'+encodeURIComponent(selected)+'/frames/'+index+'.jpg?kind='+kind;
  $('replayCount').textContent=(index+1)+' / '+scan.frames+' frames';
}
function playStep() {
  if(!playing)return;
  const scan=scans.find(s=>s.id===selected);if(!scan)return;
  let next=Number($('scrubber').value)+1;if(next>=scan.frames)next=0;
  $('scrubber').value=next;replayFrame();playTimer=setTimeout(playStep,250);
}
function selectScan(id) {selected=id;$('scrubber').value=0;drawScans();replayFrame();updateDownloads();renderState();}
function drawScans() {
  const list=$('scanList');list.replaceChildren();
  if(!scans.length){const p=document.createElement('p');p.className='empty-list';p.textContent='No recordings yet. Your first capture will appear here.';list.append(p);}
  for(const scan of scans){const b=document.createElement('button');b.className='scan-card'+(scan.id===selected?' selected':'');const title=document.createElement('strong');title.textContent=scan.id;const detail=document.createElement('span');detail.textContent=scan.frames+' frames · '+(scan.recording?'Recording':scan.reconstructed?'3D ready':'Captured');b.append(title,detail);b.onclick=()=>selectScan(scan.id);list.append(b);}
}
function updateDownloads() {
  const scan=scans.find(s=>s.id===selected);$('downloads').replaceChildren();
  if(!scan)return;
  for(const file of scan.files.filter(n=>['cloud.ply','mesh.ply','mesh.obj','alignment.png'].includes(n))){const a=document.createElement('a');a.href='/api/scans/'+encodeURIComponent(selected)+'/files/'+file;a.textContent='↓ '+file;a.download=file;$('downloads').append(a);}
}
async function refreshScans(){scans=await api('/api/scans');if(!selected&&scans.length)selected=scans[0].id;drawScans();updateDownloads();lastScanRefresh=Date.now();}
function renderState(){
  $('statusLabel').textContent=state.busy?'Reconstructing':state.recording?'Recording':state.mode==='error'?'Needs attention':state.camera_ready?'Camera ready':'Standby';
  $('statusDot').className=state.mode==='error'?'error':state.recording?'recording':state.camera_ready?'ready':'';
  $('frameCount').textContent=state.frames||0;
  const elapsed=Math.floor(state.elapsed||0);$('elapsed').textContent=String(Math.floor(elapsed/60)).padStart(2,'0')+':'+String(elapsed%60).padStart(2,'0');
  $('start').classList.toggle('hidden',!!state.recording);$('stop').classList.toggle('hidden',!state.recording);$('stop').disabled=!!state.busy;
  $('start').disabled=!!state.busy||!live;$('frameLimit').disabled=!!state.recording;
  $('preview').disabled=!!state.busy||!!state.recording;$('pause').disabled=!!state.busy||!!state.recording;
  const scan=scans.find(s=>s.id===selected);$('reconstruct').disabled=!!state.busy||!!state.recording||!scan||scan.frames<2;
  $('loadModel').disabled=!scan||!scan.reconstructed||!!state.busy;
  message(state.message||'Ready',state.mode==='error');$('log').textContent=(state.log||[]).join('\n')||'No reconstruction running.';
  if(state.busy)$('logPanel').open=true;
  if(live){$('rgbEmpty').textContent=state.busy?'Preview paused during reconstruction':state.message||'Start the preview';$('depthEmpty').textContent=state.busy?'Reconstruction runs offline':'Aligned stereo depth';}
}
async function poll(){try{
  state=await api('/api/state');if(Date.now()-lastScanRefresh>3000)await refreshScans();
  if(state.recording&&state.scan&&selected!==state.scan){selected=state.scan;drawScans();}
  renderState();if(previousBusy&&!state.busy&&state.mode!=='error'){await refreshScans();selected=state.scan;drawScans();updateDownloads();loadModel();}
  previousBusy=!!state.busy;
}catch(e){message('Connection lost. Check that the Nano is online.',true);$('statusLabel').textContent='Disconnected';}setTimeout(poll,1000);}
function initViewer(){
  if(renderer)return true;
  try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputEncoding=THREE.sRGBEncoding;$('viewer').append(renderer.domElement);scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(45,1,0.001,1000);controls=new THREE.OrbitControls(camera,renderer.domElement);controls.enableDamping=true;scene.add(new THREE.HemisphereLight(0xffffff,0x58645b,1.4));const light=new THREE.DirectionalLight(0xffffff,.7);light.position.set(2,4,3);scene.add(light);const resize=()=>{const box=$('viewer');renderer.setSize(box.clientWidth,box.clientHeight);camera.aspect=box.clientWidth/box.clientHeight;camera.updateProjectionMatrix();};window.addEventListener('resize',resize);resize();const tick=()=>{requestAnimationFrame(tick);controls.update();renderer.render(scene,camera);};tick();return true;}catch(e){message('3D viewing requires WebGL in your browser. You can still download the model.',true);return false;}
}
function fit(){if(!sphere)return;const r=Math.max(sphere.radius,.05);controls.target.copy(sphere.center);camera.position.copy(sphere.center).add(new THREE.Vector3(r*1.6,r*.8,r*2.2));camera.near=r/1000;camera.far=r*100;camera.updateProjectionMatrix();controls.update();}
async function loadModel(){
  const scan=scans.find(s=>s.id===selected);if(!scan||!scan.reconstructed)return message('Reconstruct this recording first.');if(!initViewer())return;
  const id=selected,type=$('modelType').value;$('modelName').textContent='LOADING MODEL…';
  try{const response=await fetch('/api/scans/'+encodeURIComponent(id)+'/files/'+type+'?t='+Date.now());if(!response.ok)throw Error('Model download failed');const geometry=new THREE.PLYLoader().parse(await response.arrayBuffer());geometry.rotateX(Math.PI);geometry.computeBoundingSphere();
  if(object){scene.remove(object);object.geometry.dispose();object.material.dispose();}
  if(type==='cloud.ply'){object=new THREE.Points(geometry,new THREE.PointsMaterial({size:.008,vertexColors:!!geometry.attributes.color,color:geometry.attributes.color?0xffffff:0xd3f797}));}else{geometry.computeVertexNormals();object=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({vertexColors:!!geometry.attributes.color,color:geometry.attributes.color?0xffffff:0xc5d9c2,roughness:.85,side:THREE.DoubleSide}));}
  scene.add(object);sphere=geometry.boundingSphere;fit();$('modelEmpty').classList.add('hidden');$('modelName').textContent=id;
  }catch(e){$('modelName').textContent='MODEL UNAVAILABLE';message(e.message,true);}
}
$('preview').onclick=()=>{mode(true);action('/api/preview/start');};$('pause').onclick=()=>action('/api/preview/stop');
$('start').onclick=()=>action('/api/capture/start',{frames:Number($('frameLimit').value)});$('stop').onclick=()=>action('/api/capture/stop');
$('liveMode').onclick=()=>mode(true);$('replayMode').onclick=()=>mode(false);$('scrubber').oninput=replayFrame;
$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'Pause':'Play';if(playing)playStep();else clearTimeout(playTimer);};
$('refresh').onclick=()=>refreshScans().catch(e=>message(e.message,true));
$('reconstruct').onclick=()=>{playing=false;clearTimeout(playTimer);$('play').textContent='Play';action('/api/reconstruct',{scan:selected,voxel:Number($('voxel').value),min_depth:Number($('minimum').value),max_depth:Number($('maximum').value)});};
$('loadModel').onclick=loadModel;$('fit').onclick=fit;$('modelType').onchange=()=>{if(object)loadModel();};
for(const id of ['rgb','depth'])$(id).onload=()=>$(id).classList.add('loaded');
imagesLive();refreshScans().then(()=>poll()).catch(()=>poll());
