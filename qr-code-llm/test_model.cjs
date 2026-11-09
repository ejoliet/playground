const fs=require('node:fs');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const QLM=require('./model.js');
const bytes=fs.readFileSync('artifacts/model.bin');
const fixture=JSON.parse(fs.readFileSync('artifacts/parity.json'));
assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'),fixture.sha256);
const model=QLM.decode(bytes);
let state=new Float64Array(model.h), maxError=0;
for(let i=0;i<fixture.sequence.length;i++) {
  const result=QLM.step(model,model.vocab.indexOf(fixture.sequence[i]),state); state=result.state;
  const expected=fixture.checkpoints.find(x=>x.position===i);
  if(expected) for(const key of ['state','logits']) {
    result[key].forEach((x,j)=>{const error=Math.abs(x-expected[key][j]); maxError=Math.max(maxError,error);assert.ok(error<1e-4,`${key} ${i}/${j}: ${error}`);});
  }
}
const a=QLM.generate(model,'alice ',400,.8,123);
assert.equal(a,QLM.generate(model,'alice ',400,.8,123));
assert.notEqual(a,QLM.generate(model,'alice ',400,.8,124));
assert.equal(a.length,406); assert.ok([...a].every(c=>model.vocab.includes(c)));
for(const length of [0,10,bytes.length-1]) assert.throws(()=>QLM.decode(bytes.slice(0,length)));
const bad=Buffer.from(bytes); bad[50]^=1; assert.throws(()=>QLM.decode(bad),/checksum/);
function edited(fn) {const b=Buffer.from(bytes); fn(b); b.writeUInt32LE(QLM.crc32(b.subarray(0,-4)),b.length-4);return b;}
assert.throws(()=>QLM.decode(edited(b=>b[7]=255)),/dimensions/);
assert.throws(()=>QLM.decode(edited(b=>b[4]=3)),/dimensions/);
assert.throws(()=>QLM.decode(edited(b=>b[8]=255)),/vocabulary/);
assert.throws(()=>QLM.decode(edited(b=>b[9]=b[8])),/vocabulary/);
assert.throws(()=>QLM.decode(edited(b=>b[7]--)),/length/);
assert.throws(()=>QLM.decode(edited(b=>b.writeFloatLE(NaN,8+model.v))),/scale/);
assert.throws(()=>QLM.generate(model,'a',400,0),/settings/);
assert.throws(()=>QLM.generate(model,'a',Infinity,.8),/settings/);
assert.throws(()=>QLM.step(model,-1,state),/input/);
console.log(JSON.stringify({passed:true,bytes:bytes.length,parameters:model.parameters,maxParityError:maxError},null,2));

for(const f of JSON.parse(fs.readFileSync('artifacts/format-fixtures.json'))) {
 const m=QLM.decode(Buffer.from(f.payload,'base64'));
 let result={state:new Float64Array(m.h)};
 for(const c of 'alice ') result=QLM.step(m,m.vocab.indexOf(c),result.state);
 for(const key of ['state','logits']) result[key].forEach((x,j)=>assert.ok(Math.abs(x-f[key][j])<1e-5));
 assert.equal(m.bits,f.bits);
}
