'use strict';
const assert=require('node:assert/strict');
const {plan,translation}=require('../static/explode.js');
const ranges=[
 {file:'head/shell.stp',part:'head',center:[0,0,2],start:0,count:3},
 {file:'head/shell.stp',part:'head',center:[0,0,4],start:3,count:30},
 {file:'head/frame.stp',part:'head',center:[0,0,0],start:33,count:3},
 {file:'left_arm/cover.stp',part:'left_arm',center:[0,2,-2],start:36,count:3},
 {file:'right_arm/cover.stp',part:'right_arm',center:[0,-2,-2],start:39,count:3}
];
const before=JSON.stringify(ranges),result=plan(ranges);
const close=(a,b)=>{assert.equal(a.length,b.length);for(let i=0;i<a.length;i++)assert(Math.abs(a[i]-b[i])<1e-10,`${a} != ${b}`);};
assert.deepEqual(result.center,[0,0,.4]);
assert.equal(result.groups.length,4);
const shell=result.groups.find(g=>g.file==='head/shell.stp'),frame=result.groups.find(g=>g.file==='head/frame.stp');
assert.equal(shell.ranges.length,2);assert.equal(shell.part,'head');
assert.deepEqual(shell.center,[0,0,3]);close(shell.offset,[0,0,2.6]);
assert.deepEqual(translation(shell,0),[0,0,0]);
close(translation(shell,.5),[0,0,5.2]);close(translation(shell,1),[0,0,10.4]);
close(translation(frame,1),[0,0,-1.6]);
// Every entity from one source receives the same rigid translation.
const moved=shell.ranges.map(r=>r.center.map((value,axis)=>value+translation(shell,1)[axis]));
close(moved[1].map((value,axis)=>value-moved[0][axis]),[0,0,2]);
// Full source paths preserve separate left/right copies with identical basenames.
const left=result.groups.find(g=>g.file==='left_arm/cover.stp'),right=result.groups.find(g=>g.file==='right_arm/cover.stp');
assert(left&&right&&left!==right);assert.equal(translation(left,1)[1],8);assert.equal(translation(right,1)[1],-8);
// Absolute factors are repeatable, bounded and reset without accumulated motion.
translation(shell,1);close(translation(shell,.5),[0,0,5.2]);assert.deepEqual(translation(shell,0),[0,0,0]);
close(translation(shell,2),translation(shell,1));assert.deepEqual(translation(shell,-1),[0,0,0]);
assert.deepEqual(translation(shell,NaN),[0,0,0]);assert.equal(JSON.stringify(ranges),before);
const doubled=plan(ranges.map(r=>({...r,center:r.center.map(value=>value*2)})));
for(let i=0;i<result.groups.length;i++)close(translation(doubled.groups[i],1),translation(result.groups[i],1).map(value=>value*2));
const quick=plan([{part:'head',center:[0,0,4]},{part:'body',center:[0,0,-4]}]);
assert.deepEqual(quick.groups.map(g=>g.file),['head','body']);close(translation(quick.groups[0],1),[0,0,16]);
assert.deepEqual(plan([]),{center:[0,0,0],groups:[]});
console.log('PASS: source-part grouping, shared-source rigidity, distinct same-part motion, 0/50/100/reset, scale, paths and quick fallback');
