/* Detail-preserving source-color palettes, paired with detail_palette.py.
 * Unique colors prevent mesh tessellation from drowning tiny accents.
 * Equal RGB inputs/budgets yield the same palette on browser and server;
 * geometry paths can still sample different visible color sets.
 */
const VfPreviewPalette=(()=>{
 const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
 function rgbToLab(rgb){
  const [r,g,b]=rgb.map(v=>{v=clamp(v/255,0,1);return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
  const f=v=>v>.008856?v**(1/3):7.787*v+16/116;
  const x=f((.4124564*r+.3575761*g+.1804375*b)/.95047);
  const y=f(.2126729*r+.7151522*g+.0721750*b);
  const z=f((.0193339*r+.1191920*g+.9503041*b)/1.08883);
  return [116*y-16,500*(x-y),200*(y-z)];
 }
 function labToRgb([l,a,b]){
  const fy=(l+16)/116,f=v=>v>.206893?v**3:(v-16/116)/7.787;
  const x=f(a/500+fy)*.95047,y=f(fy),z=f(fy-b/200)*1.08883;
  return [3.2404542*x-1.5371385*y-.4985314*z,
   -.969266*x+1.8760108*y+.041556*z,.0556434*x-.2040259*y+1.0572252*z]
   .map(v=>Math.floor(clamp(255*(v>.0031308?1.055*Math.max(0,v)**(1/2.4)-.055:12.92*v),0,255)));
 }
 const distance=(a,b)=>(a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2;
 function nearest(point,centers,preserveTones=false){
  let index=0,d=Infinity;
  for(let j=0;j<centers.length;j++){const next=distance(point,centers[j])+(preserveTones&&point[0]<48?Math.max(centers[j][0]-point[0],0)**2:0);if(next<d-1e-9){d=next;index=j;}}
  return {index,d};
 }
 const pointsFor=rgb=>rgb.map(c=>rgbToLab(c).map((v,i)=>Math.floor(v*[.8,1.15,1.15][i]*1000+.5)/1000));
 const mean=points=>points.reduce((s,p)=>s.map((v,i)=>v+p[i]),[0,0,0]).map(v=>v/points.length);
 function assign(points,centers){const labels=[],dist=[];for(const p of points){const n=nearest(p,centers);labels.push(n.index);dist.push(n.d);}return {labels,dist};}
 const average=a=>a.reduce((s,v)=>s+v,0)/a.length;
 const largest=a=>{let j=0;for(let i=1;i<a.length;i++)if(a[i]>a[j])j=i;return j;};
 function fit(points,k){
  let dark=0,light=0;for(let i=1;i<points.length;i++){if(points[i][0]<points[dark][0])dark=i;if(points[i][0]>points[light][0])light=i;}
  const anchors=k>=3&&points[light][0]-points[dark][0]>=32?[dark,light]:[],seeds=[...new Set([dark,light,nearest(mean(points),points).index])];
  let best=null,bestScore=Infinity;
  for(const seed of seeds){let ids=[...new Set([...anchors,seed])].slice(0,k),{dist}=assign(points,ids.map(i=>points[i]));
   while(ids.length<k){const remaining=dist.slice();for(const i of ids)remaining[i]=-1;const next=largest(remaining);ids.push(next);dist=dist.map((d,i)=>Math.min(d,distance(points[i],points[next])));}
   for(let iteration=0;iteration<8;iteration++){const {labels}=assign(points,ids.map(i=>points[i])),updated=ids.slice();
    for(let j=0;j<ids.length;j++){const old=ids[j];if(anchors.includes(old))continue;const members=[];for(let i=0;i<labels.length;i++)if(labels[i]===j)members.push(i);if(!members.length)continue;const cluster=members.map(i=>points[i]),candidate=members[nearest(mean(cluster),cluster).index];
     if(average(cluster.map(p=>distance(p,points[candidate])))<average(cluster.map(p=>distance(p,points[old])))-1e-9)updated[j]=candidate;}
    if(updated.every((v,i)=>v===ids[i]))break;ids=updated;
   }
   dist=assign(points,ids.map(i=>points[i])).dist;const score=average(dist)+.25*dist[largest(dist)];if(score<bestScore-1e-9){best=ids;bestScore=score;}
  }return [...new Set(best)].sort((a,b)=>a-b);
 }
 function quantize(colors,maxColors,start=0,end=colors.length){
  const limit=clamp(Math.floor(Number(maxColors)||8),1,512),codes=new Map();
  const codeAt=i=>{const r=clamp(Math.round(colors[i]*255),0,255),g=clamp(Math.round(colors[i+1]*255),0,255),b=clamp(Math.round(colors[i+2]*255),0,255);return r*65536+g*256+b;};
  for(let i=start;i<end;i+=3)codes.set(codeAt(i),0);
  const keys=[...codes.keys()].sort((a,b)=>a-b),rgb=keys.map(c=>[(c>>>16)&255,(c>>>8)&255,c&255]);
  if(!keys.length)return [];
  let palette=rgb;
  if(keys.length>limit){
   const lab=pointsFor(rgb),ids=fit(lab,limit),centers=ids.map(i=>lab[i]);palette=ids.map(i=>rgb[i]);
   keys.forEach((c,i)=>codes.set(c,nearest(lab[i],centers,true).index));
  }else keys.forEach((c,i)=>codes.set(c,i));
  for(let i=start;i<end;i+=3){const c=palette[codes.get(codeAt(i))];for(let axis=0;axis<3;axis++)colors[i+axis]=c[axis]/255;}
  return palette;
 }
 function apply(colors,options){return quantize(colors,options.maxColors);}
 return {apply,quantize,rgbToLab,labToRgb};
})();
