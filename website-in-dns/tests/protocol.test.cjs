const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
vm.runInThisContext(fs.readFileSync('src/transport.js','utf8'));
test('TXT strings concatenate within an RR, including DNS escapes',()=>{
  assert.equal(txt('"abc" "def\\032ghi\\\""'),'abcdef ghi"');
  assert.equal(txt('wd1:0:abcd'),'wd1:0:abcd');
  assert.throws(()=>txt('"unterminated'));
  assert.throws(()=>txt('"a" junk'));
  assert.throws(()=>txt('"\\999"'));
});
test('strict base64 rejects corruption',()=>{
  assert.equal(new TextDecoder().decode(decode64('aGVsbG8=')),'hello');
  assert.throws(()=>decode64('aGVsbG8=!'));
});
test('manifest bounds reject excessive resource requests',()=>{
  const record=JSON.parse(fs.readFileSync('dist/records.json')).at(-1);
  const {m}=parseManifest(record.content); assert.equal(m.v,1);
  for(const mutation of [{chunks:100000},{decodedBytes:9000000},{release:'../../x'},{encoding:'zip'},{sha256:'bad'}]){
    const value='wd1:m:'+Buffer.from(JSON.stringify({...m,...mutation})).toString('base64');
    assert.throws(()=>parseManifest(value));
  }
});
test('parallel fetching preserves ordering and caps concurrency',async()=>{
  let active=0,max=0;
  const result=await mapLimit([0,1,2,3,4],2,async(i)=>{active++;max=Math.max(max,active);await new Promise(r=>setTimeout(r,8-i));active--;return i});
  assert.deepEqual(result,[0,1,2,3,4]);assert.equal(max,2);
});
test('real build round-trips; truncated, corrupted, oversized gzip fails',async()=>{
  const records=JSON.parse(fs.readFileSync('dist/records.json'));
  const {m}=parseManifest(records.at(-1).content);
  const bytes=decode64(records.slice(0,-1).map((r,i)=>r.content.slice(('wd1:'+i+':').length)).join(''));
  assert.equal(await digest(bytes),m.sha256);
  const html=await inflateBounded(bytes,m.decodedBytes);
  assert.equal(html,fs.readFileSync('dist/app.html','utf8'));
  await assert.rejects(inflateBounded(bytes,m.decodedBytes-1));
  await assert.rejects(inflateBounded(bytes.subarray(0,bytes.length-8),m.decodedBytes));
});
test('a failed parallel batch drains pending requests before allowing a retry',async()=>{
  let active=0;
  await assert.rejects(mapLimit([0,1,2,3],2,async i=>{
    active++;
    try{await new Promise(r=>setTimeout(r,i===0?1:20));if(i===0)throw Error('missing');}
    finally{active--;}
  }));
  assert.equal(active,0);
});
