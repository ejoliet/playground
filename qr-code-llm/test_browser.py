"""End-to-end tests in Chromium, including actual jsQR decode and offline reload."""
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading
import time

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
import qrcode

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'.cache'
CACHE.mkdir(exist_ok=True)

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args): pass

# Feed a digital rendering of the actual final QR through Chromium's camera API.
qr=Image.open(ROOT/'artifacts/model-qr.png').convert('RGB')
size=qr.width//8*5  # exactly five pixels per QR module, including quiet zone
qr=qr.resize((size,size),Image.Resampling.NEAREST)
frame=Image.new('RGB',(1920,1080),'#e8e8e8')
frame.paste(qr,((1920-size)//2,(1080-size)//2))
yuv=np.asarray(frame.convert('YCbCr'))
y=yuv[:,:,0].tobytes()
u=yuv[:,:,1].reshape(540,2,960,2).mean(axis=(1,3)).astype('uint8').tobytes()
v=yuv[:,:,2].reshape(540,2,960,2).mean(axis=(1,3)).astype('uint8').tobytes()
camera=CACHE/'camera.y4m'
with camera.open('wb') as f:
    f.write(b'YUV4MPEG2 W1920 H1080 F5:1 Ip A1:1 C420jpeg\n')
    for _ in range(5): f.write(b'FRAME\n'+y+u+v)
qrcode.make('https://example.com/not-a-model').save(CACHE/'wrong-qr.png')

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(ROOT)))
threading.Thread(target=server.serve_forever,daemon=True).start()
url=f'http://127.0.0.1:{server.server_port}/'
checks=[]
errors=[]
requests=[]
started=time.monotonic()
try:
    parity=json.loads(subprocess.check_output(['node','test_model.cjs'],cwd=ROOT))
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM','/usr/bin/chromium'),headless=True,args=[
            '--no-sandbox','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',
            f'--use-file-for-fake-video-capture={camera}'])
        context=browser.new_context(viewport={'width':1440,'height':1100},permissions=['camera'])
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append(request.url))
        page.goto(url)
        page.wait_for_function("document.getElementById('offline').textContent.includes('saved')")
        assert page.locator('#generate').is_disabled()
        checks.append('Reader starts without model weights')
        page.locator('#image').set_input_files(str(ROOT/'artifacts/model-qr.png'))
        page.wait_for_function("document.getElementById('scanStatus').textContent.includes('checksum verified')")
        page.locator('#generate').click()
        page.wait_for_function("document.getElementById('output').textContent.length===406")
        first=page.locator('#output').inner_text()
        # Compare through the same engine with the original file, independently of jsQR output.
        original=list((ROOT/'artifacts/model.bin').read_bytes())
        expected=page.evaluate("bytes => QLM.generate(QLM.decode(bytes),'alice ',400,.8,123)",original)
        assert first==expected
        checks.append('PNG decoded from raw QR binary; generation matches original model')
        page.locator('#image').set_input_files(str(CACHE/'wrong-qr.png'))
        page.wait_for_function("document.getElementById('scanStatus').textContent.includes('not a QLM1')")
        assert page.locator('#generate').is_enabled()
        checks.append('Non-model QR rejected; loaded valid model preserved')
        page.locator('#start').click()
        page.wait_for_function("document.getElementById('scanStatus').textContent.includes('checksum verified')",timeout=45000)
        assert page.locator('#video').is_hidden()
        assert page.evaluate("document.getElementById('video').srcObject === null")
        checks.append('Camera API decoded final QR from video; camera stopped after success')
        # Ensure the service worker controls the page, then go completely offline.
        page.wait_for_function('navigator.serviceWorker.controller !== null')
        cached=page.evaluate("async () => {const c=await caches.open('qr-code-llm-reader-v1');return (await c.keys()).map(r=>r.url)}")
        assert not any('/artifacts/' in item for item in cached)
        context.set_offline(True)
        page.reload()
        page.wait_for_function("document.getElementById('offline').textContent.includes('saved')")
        assert page.locator('#generate').is_disabled()
        page.locator('#image').set_input_files(str(ROOT/'artifacts/model-qr.png'))
        page.wait_for_function("document.getElementById('scanStatus').textContent.includes('checksum verified')")
        page.locator('#generate').click()
        page.wait_for_function("document.getElementById('output').textContent.length===406")
        assert page.locator('#output').inner_text()==first
        checks.append('Offline reload, rescan, and deterministic generation passed')
        # Camera API itself must also work while offline, not just image upload.
        page.locator('#start').click()
        page.wait_for_function("document.getElementById('scanStatus').textContent.includes('checksum verified')",timeout=45000)
        assert page.locator('#start').is_enabled()
        assert page.locator('#stop').is_disabled()
        assert page.evaluate("document.getElementById('video').srcObject === null")
        checks.append('Camera scanning works with network disabled')
        page.screenshot(path=str(ROOT/'artifacts/reader-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(ROOT/'artifacts/reader-mobile.png'),full_page=True)
        checks.append('390-pixel mobile layout has no horizontal overflow')
        assert not any('.bin' in item for item in requests)
        assert all(item.startswith(url) or item.startswith('blob:'+url) or item.startswith('data:') for item in requests)
        assert not errors, errors
        checks.append('No model fetch, external request, or JavaScript page error')
        browser.close()
    record=dict(passed=True,seconds=round(time.monotonic()-started,2),model_sha256=hashlib.sha256((ROOT/'artifacts/model.bin').read_bytes()).hexdigest(),parity=parity,checks=checks,
                limitations=['Digital video camera fixture; no physical print or real camera tested','Chromium only; Safari and Firefox not tested'])
    (ROOT/'artifacts/verification.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
finally:
    server.shutdown()
