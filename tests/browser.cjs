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
