/* Shared display-only lighting. Geometry, palette and export data are untouched. */
(function(root){
 'use strict';
 const installed=new WeakSet();
 function material(options){
  const mat=new THREE.MeshLambertMaterial(options);
  mat.userData.vfPreviewLighting=true;mat.userData.vfPreviewUniform={value:1};
  // Pixel solids retain internal walls. Back-face shadow casting exposes those
  // walls as a grid on otherwise coplanar outer faces.
  mat.shadowSide=THREE.FrontSide;
  mat.onBeforeCompile=shader=>{
   shader.uniforms.vfPreviewLit=mat.userData.vfPreviewUniform;
   shader.fragmentShader='uniform float vfPreviewLit;\n'+shader.fragmentShader;
   shader.fragmentShader=shader.fragmentShader.replace('gl_FragColor = vec4( outgoingLight, diffuseColor.a );',
    'outgoingLight = mix(diffuseColor.rgb + totalEmissiveRadiance, outgoingLight, vfPreviewLit);\ngl_FragColor = vec4( outgoingLight, diffuseColor.a );');
  };
  mat.customProgramCacheKey=()=> 'vf-preview-lighting-v1';
  return mat;
 }
 function install(scene,renderer){
  if(installed.has(renderer))return;
  installed.add(renderer);const enabled={value:1};
  const ambient=new THREE.AmbientLight(0xffffff,.50),key=new THREE.DirectionalLight(0xffffff,.52),fill=new THREE.DirectionalLight(0xffffff,.16);
  key.castShadow=true;key.shadow.mapSize.set(2048,2048);key.shadow.bias=-.00015;
  key.shadow.radius=2;
  scene.add(ambient,key,fill,key.target,fill.target);
  renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.shadowMap.autoUpdate=false;
  const host=renderer.domElement.parentElement;
  const button=host.querySelector('[data-preview-lighting-toggle]');
  const setEnabled=value=>{enabled.value=value?1:0;renderer.shadowMap.enabled=value;renderer.shadowMap.needsUpdate=true;};
  if(button){
   const language=()=>{
    const en=root.vfI18n?.lang==='en';button.textContent=en?'Shadows':'阴影';
    button.title=en?'Toggle lighting and shadows; off shows original colors. Exports are unchanged.':'开关光影；关闭后查看原色，不影响导出。';
    button.setAttribute('aria-label',en?'Toggle lighting and shadows':'开关光影');
   };
   language();root.vfI18n?.onChange(language);
   button.setAttribute('aria-pressed','true');button.classList.toggle('on',true);
   button.addEventListener('click',()=>{const on=!enabled.value;setEnabled(on);button.classList.toggle('on',on);button.setAttribute('aria-pressed',String(on));});
  }
  const render=renderer.render.bind(renderer),cache=new WeakMap(),bounds=new THREE.Box3(),box=new THREE.Box3(),center=new THREE.Vector3(),size=new THREE.Vector3(),offset=new THREE.Vector3(),previousCamera=new THREE.Matrix4();
  let previousObjects='',previousSize='',lastCamera=null;
  renderer.render=function(current,camera){
   if(current!==scene)return render(current,camera);
   scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);bounds.makeEmpty();let dirty=false;const ids=[];
   scene.traverseVisible(object=>{
    if(!object.isMesh||!object.material?.userData?.vfPreviewLighting)return;
    object.material.userData.vfPreviewUniform=enabled;
    const g=object.geometry,pos=g.getAttribute('position');if(!pos)return;
    let saved=cache.get(object);
    if(!saved||saved.geometry!==g||saved.position!==pos||saved.version!==pos.version){
     g.computeVertexNormals();g.computeBoundingBox();
     saved={geometry:g,position:pos,version:pos.version,matrix:new THREE.Matrix4(),wire:!object.material.wireframe};cache.set(object,saved);dirty=true;
    }
    if(!saved.matrix.equals(object.matrixWorld)||saved.wire!==object.material.wireframe){dirty=true;saved.matrix.copy(object.matrixWorld);saved.wire=object.material.wireframe;}
    // Translucent guides/highlights remain visible but do not hide real parts.
    const solid=object.material.opacity>=.5&&!object.material.wireframe;
    object.castShadow=solid;object.receiveShadow=solid;
    if(solid){bounds.union(box.copy(g.boundingBox).applyMatrix4(object.matrixWorld));ids.push(object.id);}
   });
   if(!bounds.isEmpty()){
    bounds.getCenter(center);bounds.getSize(size);const extent=Math.max(size.length(),1),half=extent*.55;
    // Keep the receiver offset proportional to a shadow texel, including small
    // models and exploded views. A fixed millimetre offset produces acne as
    // the shadow frustum grows. This changes only shadow lookup coordinates.
    key.shadow.normalBias=(2*half/key.shadow.mapSize.x)*1.5;
    // Fixed 0.1..2000 (or 10000) camera clipping wastes depth precision in
    // exploded views: internal voxel walls then bleed through outer surfaces.
    // Fit depth only; retain FOV, target and model coordinates for picking/export.
    if(camera.isPerspectiveCamera){
     box.copy(bounds).applyMatrix4(camera.matrixWorldInverse);
     const near=Math.max(extent*.0001,-box.max.z*.5);
     const far=Math.max(near*2,-box.min.z+extent*2);
     if(camera.near!==near||camera.far!==far){camera.near=near;camera.far=far;camera.updateProjectionMatrix();}
    }
    const signature=[center.x,center.y,center.z,extent].join(',');
    if(signature!==previousSize){dirty=true;previousSize=signature;const c=key.shadow.camera;c.left=c.bottom=-half;c.right=c.top=half;c.near=extent*.5;c.far=extent*3.5;c.updateProjectionMatrix();}
    if(lastCamera!==camera||!previousCamera.equals(camera.matrixWorld)){dirty=true;lastCamera=camera;previousCamera.copy(camera.matrixWorld);}
    offset.set(-.65,.85,1.4).normalize().applyQuaternion(camera.quaternion).multiplyScalar(extent*2);key.position.copy(center).add(offset);key.target.position.copy(center);
    offset.set(1,-.3,.4).normalize().applyQuaternion(camera.quaternion).multiplyScalar(extent*2);fill.position.copy(center).add(offset);fill.target.position.copy(center);
   }
   const objects=ids.join(',');if(objects!==previousObjects){dirty=true;previousObjects=objects;}
   if(dirty)renderer.shadowMap.needsUpdate=true;
   return render(current,camera);
  };
 }
 root.VfPreviewLighting={material,install};
})(window);
