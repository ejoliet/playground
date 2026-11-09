'use strict';
const $ = id => document.getElementById(id);
let model=null, stream=null, frame=null, scanning=false, cameraSession=0;
const video=$('video'), canvas=$('canvas'), ctx=canvas.getContext('2d',{willReadFrequently:true});
function status(message,error=false) { $('scanStatus').textContent=message; $('scanStatus').classList.toggle('error',error); }
function stopCamera() {
  cameraSession++; scanning=false;
  if(frame) cancelAnimationFrame(frame);
  if(stream) stream.getTracks().forEach(t=>t.stop());
  stream=null; video.srcObject=null; video.hidden=true;
  $('cameraHint').hidden=false; $('start').disabled=false; $('stop').disabled=true;
}
function accept(bytes) {
  const decoded=QLM.decode(bytes); // Validate completely before replacing a working model.
  model=decoded; stopCamera(); $('generate').disabled=false;
  $('modelInfo').textContent=`${model.bytes.toLocaleString()} bytes · ${model.parameters.toLocaleString()} parameters · ${model.h} GRU units · ${model.bits}-bit weights`;
  status('Model decoded and checksum verified. Ready to generate offline.');
}
function scan(source,width,height) {
  // Keep enough pixels per module for a version-40 symbol. Bound giant photo memory.
  const scale=Math.min(1,1800/Math.max(width,height));
  canvas.width=Math.round(width*scale); canvas.height=Math.round(height*scale);
  ctx.drawImage(source,0,0,canvas.width,canvas.height);
  const pixels=ctx.getImageData(0,0,canvas.width,canvas.height);
  const code=jsQR(pixels.data,pixels.width,pixels.height,{inversionAttempts:'dontInvert'});
  if(code) { accept(code.binaryData); return true; }
  return false;
}
let lastScan=0;
function tick(now) {
  if(!scanning) return;
  if(video.readyState>=2 && now-lastScan>350) {
    lastScan=now;
    try { if(scan(video,video.videoWidth,video.videoHeight)) return; }
    catch(error) { status(error.message,true); }
  }
  frame=requestAnimationFrame(tick);
}
$('start').onclick=async()=>{
  stopCamera(); const session=cameraSession;
  if(!navigator.mediaDevices?.getUserMedia) {status('Camera access needs HTTPS or localhost. You can also choose a QR image.',true);return;}
  $('start').disabled=true; $('stop').disabled=false; status('Requesting camera access…');
  try {
    const acquired=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1920},height:{ideal:1080}},audio:false});
    if(session!==cameraSession) {acquired.getTracks().forEach(t=>t.stop());return;}
    stream=acquired; video.srcObject=stream; video.hidden=false; $('cameraHint').hidden=true;
    await video.play();
    if(session!==cameraSession) return;
    scanning=true; status('Scanning… fill the frame with the entire QR and its white border.'); frame=requestAnimationFrame(tick);
  } catch(error) {
    if(session!==cameraSession) return;
    stopCamera(); status(`Camera unavailable (${error.name}). Allow camera permission, or choose a QR image.`,true);
  }
};
$('stop').onclick=()=>{stopCamera();status('Camera stopped.');};
$('image').onchange=async event=>{
  const file=event.target.files[0]; if(!file) return;
  stopCamera(); status('Decoding image locally…');
  const url=URL.createObjectURL(file);
  try {
    const img=new Image(); img.src=url; await img.decode();
    if(!scan(img,img.naturalWidth,img.naturalHeight)) status('No readable QR found. Use the full-resolution image with its white border.',true);
  } catch(error) {status(error.message,true);}
  finally {URL.revokeObjectURL(url);event.target.value='';}
};
$('temperature').oninput=()=>{$('tempValue').value=Number($('temperature').value).toFixed(1);};
$('generateForm').onsubmit=async event=>{
  event.preventDefault(); if(!model) return;
  $('generate').disabled=true;
  await new Promise(resolve=>requestAnimationFrame(resolve));
  try { $('output').textContent=QLM.generate(model,$('prompt').value,400,Number($('temperature').value),Number($('seed').value)); }
  catch(error) {status(error.message,true);}
  finally {$('generate').disabled=false;}
};
window.addEventListener('pagehide',stopCamera);
document.addEventListener('visibilitychange',()=>{if(document.hidden) stopCamera();});
(async()=>{
  try {
    if(!('serviceWorker' in navigator)) throw Error();
    await navigator.serviceWorker.register('./sw.js');
    await navigator.serviceWorker.ready;
    $('offline').textContent='Reader saved for offline use';
  } catch { $('offline').textContent='Offline reload unavailable · use HTTPS or localhost'; }
})();
