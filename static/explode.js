(function(root,factory){
 if(typeof module==='object'&&module.exports)module.exports=factory();else root.VfExplode=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function plan(ranges){
  const center=[0,0,0],files=new Map();
  for(const range of ranges){
   const file=range.file||range.part,point=range.center;
   if(!file||!Array.isArray(point)||point.length!==3||!point.every(Number.isFinite))throw Error('Invalid part geometry');
   for(let axis=0;axis<3;axis++)center[axis]+=point[axis];
   if(!files.has(file))files.set(file,{file,part:range.part||file.split('/')[0],ranges:[],center:[0,0,0],offset:[0,0,0]});
   const group=files.get(file);group.ranges.push(range);
   for(let axis=0;axis<3;axis++)group.center[axis]+=point[axis];
  }
  if(ranges.length)for(let axis=0;axis<3;axis++)center[axis]/=ranges.length;
  for(const group of files.values())for(let axis=0;axis<3;axis++){
   group.center[axis]/=group.ranges.length;group.offset[axis]=group.center[axis]-center[axis];
  }
  return {center,groups:[...files.values()]};
 }
 function translation(group,factor){
  const amount=Number(factor),scale=(Number.isFinite(amount)?Math.max(0,Math.min(1,amount)):0)*4;
  return scale===0?[0,0,0]:group.offset.map(value=>value*scale);
 }
 return {plan,translation};
});
