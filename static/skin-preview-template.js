/* Plain skin surfaces only: +X front, +Y left, +Z up; origin at neck. */
const SKIN_UV={"UV_MAP":{"inner":{"head":{"top":[8,0,8,8],"bottom":[16,0,8,8],"right":[0,8,8,8],"front":[8,8,8,8],"left":[16,8,8,8],"back":[24,8,8,8]},"body":{"top":[20,16,8,4],"bottom":[28,16,8,4],"right":[16,20,4,12],"front":[20,20,8,12],"left":[28,20,4,12],"back":[32,20,8,12]},"right_arm":{"top":[44,16,4,4],"bottom":[48,16,4,4],"right":[40,20,4,12],"front":[44,20,4,12],"left":[48,20,4,12],"back":[52,20,4,12]},"left_arm":{"top":[36,48,4,4],"bottom":[40,48,4,4],"right":[32,52,4,12],"front":[36,52,4,12],"left":[40,52,4,12],"back":[44,52,4,12]},"right_leg":{"top":[4,16,4,4],"bottom":[8,16,4,4],"right":[0,20,4,12],"front":[4,20,4,12],"left":[8,20,4,12],"back":[12,20,4,12]},"left_leg":{"top":[20,48,4,4],"bottom":[24,48,4,4],"right":[16,52,4,12],"front":[20,52,4,12],"left":[24,52,4,12],"back":[28,52,4,12]}},"outer":{"head":{"top":[40,0,8,8],"bottom":[48,0,8,8],"right":[32,8,8,8],"front":[40,8,8,8],"left":[48,8,8,8],"back":[56,8,8,8]},"body":{"top":[20,32,8,4],"bottom":[28,32,8,4],"right":[16,36,4,12],"front":[20,36,8,12],"left":[28,36,4,12],"back":[32,36,8,12]},"right_arm":{"top":[44,32,4,4],"bottom":[48,32,4,4],"right":[40,36,4,12],"front":[44,36,4,12],"left":[48,36,4,12],"back":[52,36,4,12]},"left_arm":{"top":[52,48,4,4],"bottom":[56,48,4,4],"right":[48,52,4,12],"front":[52,52,4,12],"left":[56,52,4,12],"back":[60,52,4,12]},"right_leg":{"top":[4,32,4,4],"bottom":[8,32,4,4],"right":[0,36,4,12],"front":[4,36,4,12],"left":[8,36,4,12],"back":[12,36,4,12]},"left_leg":{"top":[4,48,4,4],"bottom":[8,48,4,4],"right":[0,52,4,12],"front":[4,52,4,12],"left":[8,52,4,12],"back":[12,52,4,12]}}},"ALEX_ARM_UV":{"inner":{"right_arm":{"top":[44,16,3,4],"bottom":[47,16,3,4],"right":[40,20,4,12],"front":[44,20,3,12],"left":[47,20,4,12],"back":[51,20,3,12]},"left_arm":{"top":[36,48,3,4],"bottom":[39,48,3,4],"right":[32,52,4,12],"front":[36,52,3,12],"left":[39,52,4,12],"back":[43,52,3,12]}},"outer":{"right_arm":{"top":[44,32,3,4],"bottom":[47,32,3,4],"right":[40,36,4,12],"front":[44,36,3,12],"left":[47,36,4,12],"back":[51,36,3,12]},"left_arm":{"top":[52,48,3,4],"bottom":[55,48,3,4],"right":[48,52,4,12],"front":[52,52,3,12],"left":[55,52,4,12],"back":[59,52,3,12]}}}};

function makeSkinTemplate(model,legacy=false,textureScale=1){
 if(![1,2].includes(textureScale))throw Error('Unsupported skin preview resolution');
 const arm=model==='alex'?3:4;
 const parts={head:[[8,8,8],[0,0,4]],body:[[4,8,12],[0,0,-6]],left_arm:[[4,arm,12],[0,4+arm/2,-6]],right_arm:[[4,arm,12],[0,-4-arm/2,-6]],left_leg:[[4,4,12],[0,2,-18]],right_leg:[[4,4,12],[0,-2,-18]]};
 const positions=[],uv=[],ranges=[];
 for(const [part,[baseGrid,center]] of Object.entries(parts))for(const layer of ['inner','outer']){
  if(legacy&&layer==='outer'&&part!=='head')continue;
  const expand=layer==='inner'?0:part==='head'?.5:.25;
  // Increase surface texel density while keeping every physical bound fixed.
  const grid=baseGrid.map(g=>g*textureScale);
  const low=baseGrid.map((g,i)=>center[i]-g/2-expand),high=baseGrid.map((g,i)=>center[i]+g/2+expand);
  for(const [face,axis,sign] of [['front',0,1],['back',0,-1],['left',1,1],['right',1,-1],['top',2,1],['bottom',2,-1]]){
   const axes=[0,1,2].filter(a=>a!==axis),offset=uv.length;
   for(let u=0;u<grid[axes[0]];u++)for(let v=0;v<grid[axes[1]];v++){
    const index=[0,0,0];index[axis]=sign>0?grid[axis]-1:0;index[axes[0]]=u;index[axes[1]]=v;
    let sourcePart=part,sourceFace=face;let [ix,iy,iz]=index;
    if(legacy&&part.startsWith('left_')){sourcePart=part.replace('left_','right_');iy=grid[1]-1-iy;if(face==='left')sourceFace='right';if(face==='right')sourceFace='left';}
    const table=(model==='alex'&&SKIN_UV.ALEX_ARM_UV[layer][sourcePart])||SKIN_UV.UV_MAP[layer][sourcePart];
    const [sx,sy]=table[sourceFace];const [dx,wy,hz]=grid;
    const offsets={front:[iy,hz-1-iz],back:[wy-1-iy,hz-1-iz],right:[ix,hz-1-iz],left:[dx-1-ix,hz-1-iz],top:[iy,ix],bottom:[wy-1-iy,ix]};
    const [du,dv]=offsets[sourceFace],texel=(sy*textureScale+dv)*(64*textureScale)+sx*textureScale+du;
    const corners=[[0,0],[1,0],[1,1],[0,1]].map(([a,b])=>{const p=[...center];p[axis]=sign>0?high[axis]:low[axis];p[axes[0]]=low[axes[0]]+(u+a)*(high[axes[0]]-low[axes[0]])/grid[axes[0]];p[axes[1]]=low[axes[1]]+(v+b)*(high[axes[1]]-low[axes[1]])/grid[axes[1]];return p;});
    for(const i of [0,1,2,0,2,3])positions.push(...corners[i]);uv.push(texel,texel);
   }
   ranges.push({offset,count:uv.length-offset,outer:layer==='outer',part,file:part});
  }
 }
 return {p:new Float32Array(positions),u:new Uint16Array(uv),ranges,baseScale:1,skinOnly:true,textureWidth:64*textureScale};
}
