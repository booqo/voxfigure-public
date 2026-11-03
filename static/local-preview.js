// Ordinary-body subset of the existing local preview bridge.
window.VfLocalPreview=(()=>{
 let worker=null,seq=0;const pending=new Map();
 function call(message){
  if(!worker){worker=new Worker('/static/local-preview-worker.js');worker.onmessage=({data:d})=>{const task=pending.get(d.id);if(!task)return;pending.delete(d.id);d.error?task.reject(Error(d.error)):task.resolve(d.data);};worker.onerror=e=>{for(const t of pending.values())t.reject(Error(e.message));pending.clear();worker.terminate();worker=null;};}
  const id=++seq;return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});worker.postMessage({...message,id},[message.pixels]);});
 }
 async function render(file,options){
  const bitmap=await createImageBitmap(file);
  try{
   if(!['steve','alex'].includes(options.model))throw Error('Unsupported model');
   if(![64,128].includes(bitmap.width)||![bitmap.width,bitmap.width/2].includes(bitmap.height))throw Error('Invalid skin dimensions');
   // Ordinary bodies use the existing 64-pixel geometry and sampling grid.
   const canvas=document.createElement('canvas');canvas.width=64;canvas.height=bitmap.height===bitmap.width/2?32:64;
   const context=canvas.getContext('2d');context.imageSmoothingEnabled=false;context.drawImage(bitmap,0,0,canvas.width,canvas.height);
   return call({...options,pixels:context.getImageData(0,0,canvas.width,canvas.height).data.buffer,height:canvas.height});
  }finally{bitmap.close();}
 }
 return {render};
})();
