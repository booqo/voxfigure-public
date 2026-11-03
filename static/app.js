'use strict';
const $=id=>document.getElementById(id),form=$('settings');
vfI18n.register({
 bodyType:'Body:',bodyFigure:'Articulated',model:'Model:',pixel:'Pixel mm:',colors:'Colors:',printer:'Printer:',quickPreview:'Quick Preview',generate3d:'Generate 3D',exportBtn:'Export',exportPanelTitle:'Download files',exportBaseNote:'3MF print project with colours and parts.',exportFormatLbl:'File format',tools:'Tools',theme:'Switch theme',reset:'Reset',wire:'Wire',rotate:'Rotate',axes:'Axes',explode:'Explode',mouseHint:'Left=Orbit Right=Pan Scroll=Zoom',skin:'Skin',clickUpload:'Click to upload skin PNG',origColors:'Original Colors',parts:'Parts',quantized:'Quantized',downloads:'Downloads',head:'Head',body:'Body',left_arm:'Left arm',right_arm:'Right arm',left_leg:'Left leg',right_leg:'Right leg',
 start:'Upload a skin to start',changed:'Settings changed — generate again.',skinReady:'Skin loaded. Choose Quick Preview or Generate 3D.',quickBusy:'Preparing quick preview…',quickDone:'Quick preview · Generate 3D to see the printable parts',generateBusy:'Generating model. The first run may take a few minutes…',generateDone:'Model ready · Export a coloured 3MF',exportBusy:'Preparing 3MF…',exportDone:'3MF downloaded',height:'Height ≈ {value} mm',invalidSkin:'Use a standard PNG skin, 64 or 128 pixels wide, up to 2 MB.',webglError:'3D preview could not start. Enable WebGL and reload.',optionsError:'Unable to load printer settings.',failed:'Processing failed.'
},{
 bodyType:'素体：',bodyFigure:'可动素体',model:'模型：',pixel:'像素 mm：',colors:'颜色：',printer:'打印机：',quickPreview:'快速预览',generate3d:'生成 3D',exportBtn:'导出',exportPanelTitle:'下载文件',exportBaseNote:'含颜色和分件的 3MF 打印项目。',exportFormatLbl:'文件格式',tools:'工具面板',theme:'切换深浅色',reset:'复位',wire:'线框',rotate:'旋转',axes:'坐标轴',explode:'分解',mouseHint:'左键旋转 · 右键平移 · 滚轮缩放',skin:'皮肤',clickUpload:'点击上传皮肤 PNG',origColors:'原始颜色',parts:'部件',quantized:'量化颜色',downloads:'下载',head:'头部',body:'身体',left_arm:'左臂',right_arm:'右臂',left_leg:'左腿',right_leg:'右腿',
 start:'上传皮肤开始',changed:'参数已更改，请重新生成。',skinReady:'皮肤已加载，可快速预览或生成 3D。',quickBusy:'正在快速预览…',quickDone:'快速预览 · 点击生成 3D 查看打印分件',generateBusy:'正在生成模型，首次加载需要一些时间…',generateDone:'模型已就绪，可导出彩色 3MF。',exportBusy:'正在生成 3MF…',exportDone:'3MF 已下载',height:'总高约 {value} mm',invalidSkin:'请使用 64 或 128 像素宽的标准 PNG 皮肤，文件不超过 2 MB。',webglError:'无法启动 3D 预览，请启用 WebGL 后刷新。',optionsError:'无法加载打印机设置。',failed:'处理失败。'
});
let skin=null,skinURL=null,version=0,pending=null,ready=false,optionsReady=false,canRender=true,busy=false,wire=false,downloadURL=null,statusKey='start';
function status(key,error=false){statusKey=key;$('status').textContent=vfI18n.t(key);$('status').classList.toggle('error',error);}
function heightLabel(){const n=Number($('pixelSize').value);$('modelHeight').textContent=n>=1&&n<=5?vfI18n.t('height',{value:Number((32.8*n).toFixed(1))}):'—';}
function buttons(){
 $('btnGenerate').disabled=busy||!skin||!optionsReady||!canRender;
 $('btnQuick').disabled=busy||!skin||!canRender;
 $('btnExport').disabled=busy||!ready||!optionsReady;$('btnExportGo').disabled=$('btnExport').disabled;
 for(const el of form.querySelectorAll('input,select'))el.disabled=busy||(el.id==='printerTemplate'&&!optionsReady);
 $('loading').classList.toggle('show',busy);
}
function closeExport(){$('exportPanel').hidden=true;$('btnExport').setAttribute('aria-expanded','false');}
function invalidate(){version++;pending?.abort();pending=null;busy=false;ready=false;closeExport();buttons();status('changed');heightLabel();}
vfI18n.onChange(()=>{status(statusKey);heightLabel();});vfI18n.apply();
$('vfLangBtn').addEventListener('click',vfI18n.toggle);
try{initScene();}catch(e){canRender=false;status('webglError',true);}
$('btnTheme').addEventListener('click',()=>{
 const theme=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=theme;
 try{localStorage.setItem('mc_theme',theme);}catch(e){}if(scene)scene.background=new THREE.Color(getCanvasBg());
});
$('btnTools').addEventListener('click',()=>{const collapsed=$('tools').classList.toggle('collapsed');$('btnTools').setAttribute('aria-expanded',String(!collapsed));});
function fitCamera(keepDirection=false){
 const box=new THREE.Box3().setFromObject(meshGroup);if(box.isEmpty())return;
 const sphere=box.getBoundingSphere(new THREE.Sphere());target.copy(sphere.center);
 const vertical=THREE.MathUtils.degToRad(camera.fov/2),horizontal=Math.atan(Math.tan(vertical)*camera.aspect);
 camDist=Math.max(1,sphere.radius/Math.sin(Math.min(vertical,horizontal))*1.08);
 if(!keepDirection){theta=Math.PI/4;phi=Math.acos(1/Math.sqrt(3));}
 camera.near=Math.max(.01,(camDist-sphere.radius)*.5);camera.far=Math.max(2000,camDist+sphere.radius*2);
 camera.updateProjectionMatrix();updateCamera();camera.updateMatrixWorld();
}
$('btnReset').addEventListener('click',()=>{if(meshGroup.children.length)fitCamera();else{theta=Math.PI/4;phi=Math.acos(1/Math.sqrt(3));camDist=120;target.set(0,0,-20);updateCamera();}});
function toggle(id,on){$(id).classList.toggle('on',on);$(id).setAttribute('aria-pressed',String(on));}
$('btnWire').addEventListener('click',()=>{wire=!wire;for(const m of meshGroup.children)m.material.wireframe=wire;toggle('btnWire',wire);});
$('btnRotate').addEventListener('click',()=>{isAutoRotate=!isAutoRotate;toggle('btnRotate',isAutoRotate);});
$('btnAxes').addEventListener('click',()=>{axisGroup.visible=!axisGroup.visible;toggle('btnAxes',axisGroup.visible);});
document.addEventListener('keydown',e=>{if(e.target.closest('input,select,textarea,button')||e.ctrlKey||e.altKey||e.metaKey)return;const id={w:'btnWire',r:'btnRotate',a:'btnAxes'}[e.key.toLowerCase()];if(id&&canRender)$(id).click();if(e.key==='Escape')closeExport();});
function decode(data,Type){return new Type(Uint8Array.from(atob(data),c=>c.charCodeAt(0)).buffer);}
function swatches(id,colors){$(id).replaceChildren(...colors.map(c=>{const el=document.createElement('span');el.className='sw';el.style.background=`rgb(${c.join(',')})`;el.title='#'+c.map(n=>n.toString(16).padStart(2,'0')).join('');return el;}));}
function display(data){
 while(meshGroup.children.length){const m=meshGroup.children[0];meshGroup.remove(m);m.geometry.dispose();m.material.dispose();}
 const pos=data.quick?data.positions:decode(data.positions,Float32Array),indices=data.quick?null:decode(data.colors,Uint8Array),parts=new Map();
 const ranges=data.parts.map(r=>{
  if(r.center)return r;
  const center=[0,0,0];for(let i=r.start*3;i<(r.start+r.count)*3;i+=3)for(let a=0;a<3;a++)center[a]+=pos[i+a]/r.count;
  return {...r,center};
 });
 for(const group of VfExplode.plan(ranges).groups){
  const total=group.ranges.reduce((n,r)=>n+r.count,0),positions=new Float32Array(total*3),colors=new Float32Array(total*3);let offset=0;
  for(const r of group.ranges){positions.set(pos.subarray(r.start*3,(r.start+r.count)*3),offset*3);
   if(data.quick)colors.set(data.vertexColors.subarray(r.start*3,(r.start+r.count)*3),offset*3);
   else for(let i=0;i<r.count;i++){const c=data.palette[indices[r.start+i]];for(let a=0;a<3;a++)colors[(offset+i)*3+a]=c[a]/255;}
   offset+=r.count;
  }
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));geometry.computeVertexNormals();
  const mesh=new THREE.Mesh(geometry,VfPreviewLighting.material({vertexColors:true,wireframe:wire,side:data.quick?THREE.DoubleSide:THREE.FrontSide}));
  mesh.userData={part:group.part,file:group.file,group};meshGroup.add(mesh);
  if(!parts.has(group.part))parts.set(group.part,[]);parts.get(group.part).push(mesh);
 }
 $('partToggles').replaceChildren();
 for(const [part,meshes] of parts){
  const button=document.createElement('button');button.className='part-toggle';button.dataset.i18n=part;button.textContent=vfI18n.t(part);button.setAttribute('aria-pressed','true');
  button.addEventListener('click',()=>{const visible=button.getAttribute('aria-pressed')!=='true';for(const mesh of meshes)mesh.visible=visible;button.classList.toggle('off',!visible);button.setAttribute('aria-pressed',String(visible));});$('partToggles').append(button);
 }
 $('partSection').hidden=false;$('quantPaletteSection').hidden=false;$('quantCount').textContent=data.palette.length;swatches('quantPalette',data.palette);
 $('explodeSlider').value=0;$('explodeVal').textContent='0%';$('explodeBar').hidden=false;fitCamera();
}
function explode(value){
 const factor=Math.max(0,Math.min(100,Number(value)||0))/100;$('explodeSlider').value=factor*100;$('explodeVal').textContent=(factor*100)+'%';
 for(const mesh of meshGroup.children)mesh.position.fromArray(VfExplode.translation(mesh.userData.group,factor));
 fitCamera(true);
}
$('explodeSlider').addEventListener('input',e=>explode(e.target.value));document.querySelectorAll('[data-explode]').forEach(el=>el.addEventListener('click',()=>explode(el.dataset.explode)));
for(const el of [$('modelType'),$('pixelSize'),$('maxColors'),$('printerTemplate')])el.addEventListener('change',invalidate);
$('pixelSize').addEventListener('input',heightLabel);
async function selectSkin(selected){
 if(busy)return;invalidate();skin=null;buttons();if(!selected)return;const turn=version;
 try{
  if(selected.size>2*1024*1024||!selected.name.toLowerCase().endsWith('.png'))throw Error(vfI18n.t('invalidSkin'));
  const bitmap=await createImageBitmap(selected);
  try{
   if(![64,128].includes(bitmap.width)||![bitmap.width,bitmap.width/2].includes(bitmap.height))throw Error(vfI18n.t('invalidSkin'));
   if(turn!==version)return;
   const c=document.createElement('canvas');c.width=bitmap.width;c.height=bitmap.height;const ctx=c.getContext('2d');ctx.drawImage(bitmap,0,0);const rgba=ctx.getImageData(0,0,c.width,c.height).data,palette=new Map();
   for(let i=0;i<rgba.length;i+=4)if(rgba[i+3]){const rgb=Array.from(rgba.subarray(i,i+3));palette.set(rgb.join(','),rgb);}
   swatches('origPalette',[...palette.values()]);$('origCount').textContent=palette.size;$('origPaletteSection').hidden=false;
  }finally{bitmap.close();}
  skin=selected;if(skinURL)URL.revokeObjectURL(skinURL);skinURL=URL.createObjectURL(selected);$('skinImg').src=skinURL;$('skinPreview').hidden=false;$('fileLabel').textContent=selected.name;$('uploadArea').classList.add('has-file');status('skinReady');buttons();
 }catch(e){if(turn===version)status(e.message,true);}
}
$('skinFile').addEventListener('change',()=>selectSkin($('skinFile').files[0]));
$('uploadArea').addEventListener('click',()=>{if(!busy)$('skinFile').click();});
$('uploadArea').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('uploadArea').click();}});
$('uploadArea').addEventListener('dragover',e=>e.preventDefault());$('uploadArea').addEventListener('drop',e=>{e.preventDefault();selectSkin(e.dataTransfer.files[0]);});
async function run(mode){
 if(!skin||!form.reportValidity()||busy)return;
 const data=new FormData(form);data.set('skin',skin);const turn=++version;pending?.abort();const controller=new AbortController();pending=controller;busy=true;buttons();closeExport();status(mode+'Busy');
 try{
  if(mode==='quick'){
   const result=await VfLocalPreview.render(skin,{model:$('modelType').value,scale:Number($('pixelSize').value),maxColors:Number($('maxColors').value)});
   if(turn!==version)return;display(result);ready=true;status('quickDone');
  }else{
   const response=await fetch(mode==='export'?'/api/export':'/api/generate',{method:'POST',body:data,signal:controller.signal});
   if(!response.ok){const error=await response.json();throw Error(error.error||vfI18n.t('failed'));}
   if(mode==='export'){
    const blob=await response.blob();if(turn!==version)return;
    if(downloadURL)URL.revokeObjectURL(downloadURL);downloadURL=URL.createObjectURL(blob);const a=document.createElement('a');a.href=downloadURL;a.download=`voxfigure-${$('modelType').value}.3mf`;a.textContent=a.download;const li=document.createElement('li');li.append(a);$('downloadList').replaceChildren(li);$('downloadSection').hidden=false;a.click();status('exportDone');
   }else{const result=await response.json();if(turn!==version)return;display(result);ready=true;status('generateDone');}
  }
 }catch(e){if(turn===version&&e.name!=='AbortError')status(e.message,true);}
 finally{if(turn===version){pending=null;busy=false;buttons();}}
}
form.addEventListener('submit',e=>{e.preventDefault();run('generate');});$('btnQuick').addEventListener('click',()=>run('quick'));$('btnExportGo').addEventListener('click',()=>run('export'));
$('btnExport').addEventListener('click',()=>{const panel=$('exportPanel');panel.hidden=!panel.hidden;$('btnExport').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden&&innerWidth>600){const r=$('btnExport').getBoundingClientRect();panel.style.top=(r.bottom+6)+'px';panel.style.right=Math.max(16,innerWidth-r.right)+'px';}});
document.addEventListener('click',e=>{if(!e.target.closest('.export-wrap'))closeExport();});window.addEventListener('resize',closeExport);
fetch('/api/options').then(r=>{if(!r.ok)throw Error(vfI18n.t('optionsError'));return r.json();}).then(data=>{
 $('printerTemplate').replaceChildren(...data.printers.map(p=>{const o=document.createElement('option');o.value=p.id;o.textContent=p.name;return o;}));optionsReady=true;buttons();
}).catch(e=>status(e.message,true));buttons();
