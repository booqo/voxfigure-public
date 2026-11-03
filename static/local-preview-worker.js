importScripts('/static/skin-preview-template.js','/static/preview-palette.js');
// Ordinary skin-only fast preview, extracted from the existing worker.
const caches=new Map();
self.onmessage=({data:m})=>{try{
 if(!['steve','alex'].includes(m.model)||!Number.isFinite(m.scale)||m.scale<=0)throw Error('Invalid preview parameters');
 const key=m.model+':'+m.height;
 if(!caches.has(key))caches.set(key,makeSkinTemplate(m.model,m.height===32));
 const d=caches.get(key),pixels=new Uint8ClampedArray(m.pixels),keep=new Uint8Array(d.u.length);let count=0;
 const sample=uv=>{const y=Math.floor(uv/64);return y>=m.height?[0,0,0,0]:pixels.subarray(uv*4,uv*4+4);};
 const parts=[];
 for(const range of d.ranges){const start=count;
  for(let i=range.offset;i<range.offset+range.count;i++){if(range.outer&&!sample(d.u[i])[3])continue;keep[i]=1;count++;}
  if(count>start)parts.push({part:range.part,start:start*3,count:(count-start)*3});
 }
 const positions=new Float32Array(count*9),colors=new Float32Array(count*9);let out=0;
 for(let i=0;i<keep.length;i++)if(keep[i]){const c=sample(d.u[i]);for(let j=0;j<9;j++){positions[out*9+j]=d.p[i*9+j]*m.scale;colors[out*9+j]=c[j%3]/255;}out++;}
 const palette=VfPreviewPalette.apply(colors,m);
 self.postMessage({id:m.id,data:{positions,vertexColors:colors,palette,parts,triangles:count,quick:true}},[positions.buffer,colors.buffer]);
}catch(e){self.postMessage({id:m.id,error:e.message});}};
