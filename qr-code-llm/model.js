/* QLM1 decoder and GRU inference. No framework, model, or network dependency. */
(function (root) {
  'use strict';
  function crc32(bytes) {
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc ^= byte;
      for (let j = 0; j < 8; j++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }
  function decode(input) {
    const bytes = Uint8Array.from(input);
    if (bytes.length < 16 || bytes.length > 2953) throw Error('Model must contain 16–2,953 bytes.');
    const dv = new DataView(bytes.buffer);
    if (String.fromCharCode(...bytes.slice(0,4)) !== 'QLM1') throw Error('This QR is not a QLM1 neural model.');
    if (crc32(bytes.slice(0,-4)) !== dv.getUint32(bytes.length-4,true)) throw Error('Model checksum failed. Please scan again.');
    const [bits,v,e,h] = bytes.slice(4,8);
    if (![4,8,32].includes(bits) || v < 2 || v > 128 || e < 1 || e > 64 || h < 1 || h > 64) throw Error('Unsupported model dimensions.');
    const alphabet = bytes.slice(8,8+v);
    if (alphabet.length !== v || alphabet.some(x => x > 126 || (x < 32 && x !== 10))) throw Error('Invalid vocabulary.');
    const vocab = String.fromCharCode(...alphabet);
    if (new Set(vocab).size !== v || !vocab.includes(' ')) throw Error('Invalid vocabulary.');
    const sizes = [v*e,3*h*e,3*h*h,3*h,3*h,v*h,v];
    const expected = 8+v+4+sizes.reduce((s,n) => s+(bits===32 ? 4*n : 4+Math.ceil(n*bits/8)),0);
    if (bytes.length !== expected) throw Error('Model length does not match its dimensions.');
    let pos = 8+v;
    const tensors = sizes.map(n => {
      const a = new Float64Array(n);
      if (bits === 32) {
        for (let i=0;i<n;i++,pos+=4) a[i]=dv.getFloat32(pos,true);
      } else {
        const scale = dv.getFloat32(pos,true); pos += 4;
        if (!Number.isFinite(scale) || scale <= 0 || scale > 100) throw Error('Invalid quantization scale.');
        for (let i=0;i<n;i++) {
          const q = bits===8 ? dv.getInt8(pos+i) : ((bytes[pos+(i>>1)] >> ((i&1)*4)) & 15)-8;
          a[i] = q*scale;
        }
        pos += Math.ceil(n*bits/8);
      }
      if (a.some(x => !Number.isFinite(x) || Math.abs(x)>1000)) throw Error('Invalid model weight.');
      return a;
    });
    return {bits,v,e,h,vocab,tensors,bytes:bytes.length,parameters:sizes.reduce((a,b)=>a+b,0)};
  }
  const sigmoid = x => 1/(1+Math.exp(-x));
  function step(model, token, state) {
    const {v,e,h,tensors:[emb,wi,wh,bi,bh,wo,bo]} = model;
    if (!Number.isInteger(token) || token<0 || token>=v || state.length!==h) throw Error('Invalid recurrent input.');
    const a = new Float64Array(3*h), b = new Float64Array(3*h);
    for (let row=0;row<3*h;row++) {
      let x=bi[row], y=bh[row];
      for(let j=0;j<e;j++) x += wi[row*e+j]*emb[token*e+j];
      for(let j=0;j<h;j++) y += wh[row*h+j]*state[j];
      a[row]=x; b[row]=y;
    }
    const next = new Float64Array(h);
    for(let j=0;j<h;j++) {
      const r=sigmoid(a[j]+b[j]), z=sigmoid(a[h+j]+b[h+j]);
      next[j]=(1-z)*Math.tanh(a[2*h+j]+r*b[2*h+j])+z*state[j];
    }
    const logits = new Float64Array(v);
    for(let i=0;i<v;i++) {
      let value=bo[i];
      for(let j=0;j<h;j++) value += wo[i*h+j]*next[j];
      logits[i]=value;
    }
    return {state:next,logits};
  }
  function random(seed) {
    let s=seed>>>0;
    return () => { s=(Math.imul(s,1664525)+1013904223)>>>0; return s/4294967296; };
  }
  function generate(model,prompt,count=400,temperature=.8,seed=123) {
    if (!Number.isFinite(temperature) || temperature<.1 || temperature>2 || !Number.isInteger(count) || count<1 || count>2000 || prompt.length>1000) throw Error('Invalid generation settings.');
    prompt=prompt.toLowerCase().split('').map(c=>model.vocab.includes(c)?c:' ').join('') || ' ';
    let state=new Float64Array(model.h), logits, out=prompt;
    for(const c of prompt) ({state,logits}=step(model,model.vocab.indexOf(c),state));
    const rng=random(seed);
    for(let k=0;k<count;k++) {
      const max=Math.max(...logits);
      const p=Array.from(logits,x=>Math.exp((x-max)/temperature));
      let target=rng()*p.reduce((a,b)=>a+b,0), token=p.length-1;
      for(let i=0;i<p.length;i++) { target-=p[i]; if(target<0) {token=i;break;} }
      out+=model.vocab[token];
      ({state,logits}=step(model,token,state));
    }
    return out;
  }
  const api={crc32,decode,step,generate};
  if (typeof module!=='undefined' && module.exports) module.exports=api;
  else root.QLM=api;
})(globalThis);
