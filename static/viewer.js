// Camera and axes extracted from the existing VoxFigure workbench.
let scene,renderer,camera,meshGroup,axisGroup;
let target=new THREE.Vector3(0,0,-20),theta=Math.PI/4,phi=Math.acos(1/Math.sqrt(3)),camDist=120,lastMouse={x:0,y:0},isAutoRotate=false;
function getCanvasBg(){return getComputedStyle(document.documentElement).getPropertyValue('--canvas-bg').trim();}
function initScene(){
    scene=new THREE.Scene();
    scene.background=new THREE.Color(getCanvasBg());
    const c=document.getElementById('canvas3d');
    renderer=new THREE.WebGLRenderer({canvas:c,antialias:true});
  VfPreviewLighting.install(scene,renderer); renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
    camera=new THREE.PerspectiveCamera(45,1,0.1,2000); camera.up.set(0,0,1);

    meshGroup=new THREE.Group(); scene.add(meshGroup);
    axisGroup = buildAxes(scene);
    resize(); updateCamera();
    // Pointer Events: unified mouse + touch handling
    const activePtrs = new Map(); // pointerId → {x, y}
    let lastPinchDist = 0;
    const _ptrList = () => [...activePtrs.values()];
    const _ptrCenter = pts => ({x:(pts[0].x+pts[1].x)/2, y:(pts[0].y+pts[1].y)/2});
    const _ptrDist = pts => Math.hypot(pts[0].x-pts[1].x, pts[0].y-pts[1].y);
    // Pan when: 2+ pointers OR mouse middle/right button held (e.buttons bitmask: 4=middle, 2=right)
    const _isPanning = e => activePtrs.size >= 2 || (e.pointerType === 'mouse' && (e.buttons & 6));
    const _panTarget = (dx, dy) => {
        const ps = camDist * 0.001;
        const cd = new THREE.Vector3().subVectors(target, camera.position).normalize();
        const cr = new THREE.Vector3().crossVectors(cd, camera.up).normalize();
        const cu = new THREE.Vector3().crossVectors(cr, cd).normalize();
        target.addScaledVector(cr, -dx*ps);
        target.addScaledVector(cu, dy*ps);
    };

    c.addEventListener('pointerdown', e=>{
        c.setPointerCapture(e.pointerId);
        activePtrs.set(e.pointerId, {x:e.clientX, y:e.clientY});
        if(e.pointerType==='mouse' && (e.button===1 || e.button===2)) e.preventDefault();
        lastMouse = {x:e.clientX, y:e.clientY};
        if(activePtrs.size===2){
            const pts=_ptrList();
            const ctr=_ptrCenter(pts);
            lastMouse={x:ctr.x,y:ctr.y};
            lastPinchDist=_ptrDist(pts);
        }
    });

    c.addEventListener('pointermove', e=>{
        if(!activePtrs.has(e.pointerId)) return;
        activePtrs.set(e.pointerId, {x:e.clientX, y:e.clientY});
        const pts=_ptrList();
        if(pts.length===1){
            const dx = e.clientX-lastMouse.x, dy = e.clientY-lastMouse.y;
            lastMouse = {x:e.clientX, y:e.clientY};
            if(_isPanning(e)){
                _panTarget(dx, dy);
            } else {
                theta-=dx*0.005;
                phi=Math.max(0.05,Math.min(Math.PI-0.05,phi-dy*0.005));
            }
            updateCamera();
        } else if(pts.length>=2){
            const ctr=_ptrCenter(pts);
            const dx=ctr.x-lastMouse.x, dy=ctr.y-lastMouse.y;
            lastMouse={x:ctr.x,y:ctr.y};
            _panTarget(dx, dy);
            const d=_ptrDist(pts);
            if(lastPinchDist>0){camDist=Math.max(5,Math.min(500,camDist*(lastPinchDist/d)));}
            lastPinchDist=d;
            updateCamera();
        }
    });

    const _ptrUp = e=>{
        activePtrs.delete(e.pointerId);
        if(activePtrs.size<=1) lastPinchDist=0;
        if(activePtrs.size===1){
            const p=_ptrList()[0]; lastMouse={x:p.x,y:p.y};
        }
    };
    c.addEventListener('pointerup', _ptrUp);
    c.addEventListener('pointercancel', _ptrUp);
    c.addEventListener('lostpointercapture', _ptrUp);
    c.addEventListener('wheel',e=>{e.preventDefault();camDist=Math.max(5,Math.min(500,camDist*(e.deltaY>0?1.08:0.92)));updateCamera();},{passive:false});
    c.addEventListener('contextmenu',e=>e.preventDefault());
    // ResizeObserver catches window resize, panel toggle, and flex layout changes via parent
    new ResizeObserver(()=>resize()).observe(c.parentElement);
    // matchMedia catches DPI changes when dragging to a monitor with different scaling
    _watchDpr();
    animate();
}
let _lastDpr=0;
function _watchDpr(){
    // matchMedia fires once when DPI changes (e.g. drag to a different monitor)
    // We re-register after each fire to keep watching
    matchMedia(`(resolution: ${devicePixelRatio}dppx)`)
        .addEventListener('change',()=>{_lastDpr=0;resize();_watchDpr();},{once:true});
}
function resize(){
    const c=renderer.domElement,p=c.parentElement;
    const dpr=window.devicePixelRatio||1;
    const w=p.clientWidth, h=p.clientHeight;
    // Skip if nothing changed (avoid redundant GPU work from multiple triggers)
    if(dpr===_lastDpr && renderer.domElement.width===Math.floor(w*dpr) && renderer.domElement.height===Math.floor(h*dpr)) return;
    _lastDpr=dpr;
    renderer.setPixelRatio(dpr);
    renderer.setSize(w,h);
    camera.aspect=w/h;
    camera.updateProjectionMatrix();
}
function updateCamera(){const sp=Math.sin(phi),cp=Math.cos(phi),st=Math.sin(theta),ct=Math.cos(theta);camera.position.set(target.x+camDist*sp*ct,target.y+camDist*sp*st,target.z+camDist*cp);camera.lookAt(target);}
function animate(){requestAnimationFrame(animate);if(isAutoRotate){theta+=0.003;updateCamera();}renderer.render(scene,camera);}
function buildAxes(scene) {
    const group = new THREE.Group();
    const len = 30;
    const axes = {x: [1,0,0,0xff4444], y: [0,1,0,0x44cc44], z: [0,0,1,0x4488ff]};
    for (const [name, [dx,dy,dz,color]] of Object.entries(axes)) {
        const dir = new THREE.Vector3(dx, dy, dz);
        const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), dir.clone().multiplyScalar(len)]);
        group.add(new THREE.Line(geo, new THREE.LineBasicMaterial({color})));
        const cone = new THREE.Mesh(new THREE.ConeGeometry(1.2, 4, 8), new THREE.MeshBasicMaterial({color}));
        cone.position.copy(dir.clone().multiplyScalar(len));
        cone.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), dir);
        group.add(cone);
        const lc = document.createElement('canvas'); lc.width = 64; lc.height = 64;
        const ctx = lc.getContext('2d'); ctx.font = 'bold 48px sans-serif';
        ctx.fillStyle = '#' + color.toString(16).padStart(6, '0');
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(name.toUpperCase(), 32, 32);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(lc), depthTest: false}));
        sprite.position.copy(dir.clone().multiplyScalar(len + 5)); sprite.scale.set(6, 6, 1);
        group.add(sprite);
    }
    scene.add(group);
    return group;
}
