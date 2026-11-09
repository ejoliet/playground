// Intercepted DoH is explicitly a fixture, never evidence of DNS publication.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const http=require('node:http');
(async()=>{
  const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const records=JSON.parse(fs.readFileSync('dist/records.json'));
  const results={mode:'intercepted DoH fixture; not live DNS',checks:[],requests:[]};
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(() => { Math.random = () => 0; });
  let failure='',calls=0;
  await context.route(/^https:\/\/(dns.google|cloudflare-dns.com)\//,async route=>{
    const url=new URL(route.request().url()),name=url.searchParams.get('name');
    calls++;results.requests.push({name,type:url.searchParams.get('type')});
    if(name==='example.com')return route.fulfill({contentType:'application/dns-json',body:JSON.stringify({Status:0,Answer:[{name:'example.com.',type:16,TTL:300,data:'fixture-only'}]}),headers:{'Access-Control-Allow-Origin':'*'}});
    const r=records.find(r=>r.name===name);
    if(failure==='http')return route.fulfill({status:503,body:'unavailable'});
    let answer=r?{Status:0,TC:false,Answer:[{name:name+'.',type:16,TTL:60,data:r.content.match(/.{1,255}/g).map(s=>'"'+s+'"').join(' ')}]}:{Status:3};
    if(failure==='missing'&&name.startsWith('c0.'))answer={Status:0};
    if(failure==='corrupt'&&name.startsWith('c0.'))answer.Answer[0].data=answer.Answer[0].data.replace('H4sI','AAAA');
    if(failure==='duplicate'&&r)answer.Answer.push(answer.Answer[0]);
    return route.fulfill({contentType:'application/dns-json',body:JSON.stringify(answer),headers:{'Access-Control-Allow-Origin':'*'}});
  });
  const page=await context.newPage();let errors=[];page.on('pageerror',e=>errors.push(e.message));
  const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end(fs.readFileSync('index.html'))});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const address='http://127.0.0.1:'+server.address().port;
  await page.goto(address);
  await page.getByRole('button',{name:'Load from DNS',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Verified'));
  assert.equal(calls,records.length);results.checks.push('all document bytes fetched through fixture TXT records; exact query count');
  const frame=page.frameLocator('#app');
  await frame.getByRole('heading',{name:'A small world, inside a TXT record.'}).waitFor();
  await page.screenshot({path:'evidence/desktop.png',fullPage:true});
  for(const name of ['Atlas','Notebook','Packet pairs','Resolver lab','Station']){
    await frame.getByRole('link',{name,exact:true}).click();
    assert.equal(calls,records.length);
  }
  results.checks.push('five routes work without further network requests');
  await frame.getByRole('link',{name:'Resolver lab',exact:true}).click();
  await frame.getByRole('button',{name:'Query TXT',exact:true}).click();
  await frame.locator('#query-status').filter({hasText:'DNS status 0'}).waitFor();
  assert.ok((await frame.locator('#answer').textContent()).includes('fixture-only'));
  results.checks.push('resolver inspector submits and displays fixture TXT answer');
  await frame.getByRole('link',{name:'Notebook',exact:true}).click();
  await frame.getByRole('searchbox').fill('unfindable needle');
  assert.equal(await frame.locator('article:visible').count(),0);
  await frame.getByRole('searchbox').fill('caching');
  assert.ok(await frame.locator('article:visible').count()>0);
  results.checks.push('search and empty state');
  await frame.getByRole('link',{name:'Packet pairs',exact:true}).click();
  await frame.locator('.tile').nth(0).focus();
  await page.keyboard.press('Enter');
  assert.equal(await frame.locator('.tile.revealed').count(),1);
  results.checks.push('keyboard Enter reveals a focused game tile');
  await frame.getByRole('button',{name:'New game'}).click();
  assert.equal(await frame.locator('.tile.revealed').count(),0);
  const deck=['A','AAAA','TXT','MX','NS','SOA','PTR','CAA','A','AAAA','TXT','MX','NS','SOA','PTR','CAA'];
  for(let i=deck.length-1;i>0;i--)[deck[i],deck[0]]=[deck[0],deck[i]];
  for(const label of new Set(deck)){
    const pair=deck.map((v,i)=>v===label?i:-1).filter(i=>i>=0);
    await frame.locator('.tile').nth(pair[0]).click();
    await frame.locator('.tile').nth(pair[1]).click();
  }
  assert.equal(await frame.locator('.tile.matched').count(),16);results.checks.push('complete game and restart');
  await frame.getByRole('link',{name:'Station',exact:true}).click();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'evidence/mobile.png',fullPage:true});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.ok(await page.frames()[1].evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  results.checks.push('390px mobile has no horizontal overflow');
  // Parent DOM is inaccessible to the fetched document.
  const isolated=await page.frames()[1].evaluate(()=>{try{return !!parent.document}catch{return false}});
  assert.equal(isolated,false);results.checks.push('sandbox denies parent DOM access');
  for(const mode of ['http','missing','corrupt','duplicate']){
    failure=mode;await page.getByRole('button',{name:'Load from DNS',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Load failed'));
    assert.equal(await page.locator('#app').getAttribute('srcdoc'),null);
    await page.waitForFunction(()=>!document.querySelector('#go').disabled);
    results.checks.push(mode+' failure is visible; no fallback document');
  }
  assert.deepEqual(errors,[]);results.checks.push('no uncaught JavaScript errors');
  fs.writeFileSync('evidence/browser-tests.json',JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify({checks:results.checks},null,2));
  await browser.close();server.close();
})().catch(e=>{console.error(e);process.exit(1)});
