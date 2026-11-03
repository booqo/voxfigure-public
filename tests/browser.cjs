// Run against a local instance: VF_URL=http://127.0.0.1:5000 node tests/browser.cjs
// VF_UI_ONLY=1 checks layout and unknown paths without invoking CadQuery.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_PATH?{executablePath:process.env.BROWSER_PATH}:{})});
 const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const url=process.env.VF_URL||'http://127.0.0.1:5000';
 const out=path.resolve('test-results');fs.mkdirSync(out,{recursive:true});
 const snapshot=()=>page.evaluate(()=>meshGroup.children.map(m=>({file:m.userData.file,part:m.userData.part,offset:m.userData.group.offset,position:m.position.toArray(),visible:m.visible,vertices:m.geometry.attributes.position.count,sample:Array.from(m.geometry.attributes.position.array.slice(0,9))})));
 const framing=()=>page.evaluate(()=>{
  // A previous expanded frame can leave a near plane beyond the new bounds.
  camera.near=camDist;fitCamera(true);
  meshGroup.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  const bounds=[Infinity,Infinity,Infinity,-Infinity,-Infinity,-Infinity];
  for(const mesh of meshGroup.children){
   if(!mesh.visible)continue;if(!mesh.geometry.boundingBox)mesh.geometry.computeBoundingBox();
   const box=mesh.geometry.boundingBox;
   for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
    const point=new THREE.Vector3(x,y,z).applyMatrix4(mesh.matrixWorld).project(camera);
    for(let axis=0;axis<3;axis++){bounds[axis]=Math.min(bounds[axis],point.getComponent(axis));bounds[axis+3]=Math.max(bounds[axis+3],point.getComponent(axis));}
   }
  }
  return {bounds,theta,phi,distance:camDist};
 });
 const checkExplode=async native=>{
  const baseline=await snapshot();assert.equal(new Set(baseline.map(m=>m.file)).size,baseline.length);
  if(native){
   assert(baseline.length>6,'Generated geometry must retain source parts');
   const heads=baseline.filter(m=>m.part==='head');assert(heads.length>1,'Head parts must remain separate');
   assert(new Set(heads.map(m=>JSON.stringify(m.offset))).size>1,'Head source parts need independent motion');
  }else assert.equal(baseline.length,6,'Quick preview retains skin-part fallback');
  const viewport=page.viewportSize(),angle=await page.evaluate(()=>{theta+=.37;phi=Math.min(Math.PI-.1,phi+.2);updateCamera();return {theta,phi};});
  for(const size of [{width:1440,height:1000},{width:390,height:844}]){
   await page.setViewportSize(size);await page.evaluate(()=>resize());let assembledDistance=null;
   for(const value of [0,50,100,50,0]){
    await page.locator(`[data-explode="${value}"]`).click();const state=await snapshot(),view=await framing();
    for(let i=0;i<state.length;i++){
     assert.equal(state[i].file,baseline[i].file);assert.deepEqual(state[i].sample,baseline[i].sample);assert.equal(state[i].vertices,baseline[i].vertices);
     for(let axis=0;axis<3;axis++)assert(Math.abs(state[i].position[axis]-baseline[i].offset[axis]*value/25)<1e-8,'Absolute source-part translation');
    }
    assert.equal(view.theta,angle.theta);assert.equal(view.phi,angle.phi);
    assert(view.bounds.every(v=>Number.isFinite(v)&&v>=-1-1e-6&&v<=1+1e-6),`Clipped ${value}% view at ${size.width}px: ${view.bounds}`);
    if(value===0){if(assembledDistance===null)assembledDistance=view.distance;else assert(Math.abs(view.distance-assembledDistance)<1e-8,'Reset camera must not accumulate distance');}
   }
  }
  await page.setViewportSize(viewport);await page.evaluate(()=>{resize();explode(0);});
  const head=page.locator('.part-toggle[data-i18n="head"]');await head.click();
  const hidden=await snapshot();assert(hidden.filter(m=>m.part==='head').every(m=>!m.visible));assert(hidden.filter(m=>m.part!=='head').every(m=>m.visible));await head.click();
  await page.locator('#btnWire').click();assert(await page.evaluate(()=>meshGroup.children.every(m=>m.material.wireframe)));await page.locator('#btnWire').click();
 };

 try{
  await page.goto(url,{waitUntil:'networkidle'});
  await page.waitForFunction(()=>document.getElementById('printerTemplate').disabled===false);
  assert.equal(await page.locator('#modelType option').count(),2);
  assert.equal(await page.locator('#bodyType option').count(),1);
  assert.equal(await page.locator('#btnGenerate').isDisabled(),true);
  assert.equal(await page.locator('#btnExport').isDisabled(),true);
  assert.equal(await page.locator('#viewport canvas').count(),1);
  const layout=await page.evaluate(()=>{const v=document.querySelector('.viewport').getBoundingClientRect(),t=document.querySelector('.tools').getBoundingClientRect(),b=document.querySelector('.topbar').getBoundingClientRect();return {right:t.x>=v.right-1,below:v.top>=b.bottom-1,width:t.width};});
  assert(layout.right&&layout.below&&layout.width===300,'Expected topbar/left viewport/right 300px tools layout');
  const bytes=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d');x.fillStyle='#53392d';x.fillRect(0,0,32,16);x.fillStyle='#c99574';x.fillRect(8,10,8,6);x.fillRect(40,16,16,16);x.fillRect(32,48,16,16);x.fillStyle='#219fa6';x.fillRect(16,16,24,16);x.fillRect(40,16,16,7);x.fillRect(32,48,16,7);x.fillStyle='#4d4278';x.fillRect(0,16,16,16);x.fillRect(16,48,16,16);x.fillStyle='#33333d';x.fillRect(9,11,2,1);x.fillRect(13,11,2,1);return c.toDataURL('image/png').split(',')[1];});
  await page.locator('#skinFile').setInputFiles({name:'demo-skin.png',mimeType:'image/png',buffer:Buffer.from(bytes,'base64')});
  await page.waitForFunction(()=>!document.getElementById('btnQuick').disabled);
  for(const model of ['steve','alex']){
   await page.selectOption('#modelType',model);await page.locator('#btnQuick').click();
   await page.waitForFunction(()=>document.getElementById('partToggles').children.length===6&&!document.getElementById('loading').classList.contains('show'));
   assert.equal(await page.locator('#status').evaluate(el=>el.classList.contains('error')),false);
   await checkExplode(false);
  }
  assert.equal(await page.locator('.part-toggle').count(),6);
  await page.locator('.part-toggle').first().click();assert.equal(await page.locator('.part-toggle').first().getAttribute('aria-pressed'),'false');await page.locator('.part-toggle').first().click();
  await page.locator('[data-explode="50"]').click();assert.equal(await page.locator('#explodeVal').textContent(),'50%');await page.locator('[data-explode="0"]').click();
  await page.locator('#btnLighting').click();assert.equal(await page.locator('#btnLighting').getAttribute('aria-pressed'),'false');await page.locator('#btnLighting').click();
  await page.evaluate(()=>document.activeElement.blur());await page.keyboard.press('w');assert.equal(await page.locator('#btnWire').getAttribute('aria-pressed'),'true');await page.keyboard.press('w');
  await page.locator('#vfLangBtn').click();assert.equal(await page.locator('html').getAttribute('lang'),'en');await page.locator('#vfLangBtn').click();
  if(await page.locator('html').getAttribute('data-theme')!=='dark')await page.locator('#btnTheme').click();
  await page.screenshot({path:path.join(out,'desktop-dark.png'),fullPage:true,animations:'disabled'});
  await page.locator('#btnTheme').click();await page.screenshot({path:path.join(out,'desktop-light.png'),fullPage:true,animations:'disabled'});
  await page.locator('#btnExport').click();assert(await page.locator('#exportPanel').isVisible());await page.locator('#btnExport').click();
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert(await page.evaluate(()=>document.querySelector('.tools').getBoundingClientRect().top>=document.querySelector('.viewport').getBoundingClientRect().bottom-1));
  await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
  await page.locator('#btnTools').click();assert.equal(await page.locator('#tools').isVisible(),false);await page.locator('#btnTools').click();
  for(const endpoint of ['/unknown-page','/api/unknown-operation','/api/generate/extra'])assert.equal((await page.request.get(url+endpoint)).status(),404);
  if(!process.env.VF_UI_ONLY){
   await page.locator('#btnGenerate').click();
   await page.waitForFunction(()=>!document.getElementById('loading').classList.contains('show')&&document.getElementById('status').textContent.includes('模型已就绪'),{},{timeout:900000});
   await checkExplode(true);
   await page.locator('#btnExport').click();
   const download=page.waitForEvent('download',{timeout:900000});await page.locator('#btnExportGo').click();
   await (await download).saveAs(path.join(out,'figure.3mf'));
   assert(fs.statSync(path.join(out,'figure.3mf')).size>1000);
   await page.setViewportSize({width:1440,height:1000});
   await page.locator('#btnReset').click();
   await page.screenshot({path:path.join(out,'generated.png'),fullPage:true});
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify({ui:'passed',native_generation:process.env.VF_UI_ONLY?'not_run':'passed',errors},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
