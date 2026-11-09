// Real browser requests. No routes or responses are intercepted here.
const {chromium}=require('playwright');
const fs=require('node:fs');
const http=require('node:http');
(async()=>{
  const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html');res.end(fs.readFileSync('index.html'))});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const proxy=process.env.HTTPS_PROXY||process.env.https_proxy;
  const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox'],...(proxy?{proxy:{server:proxy,bypass:'127.0.0.1,localhost'}}:{})});
  const page=await browser.newPage();
  await page.goto('http://127.0.0.1:'+server.address().port);
  const rows=await page.evaluate(async()=>{
    const rows=[];
    for(const endpoint of ['https://dns.google/resolve','https://cloudflare-dns.com/dns-query']){
      const started=performance.now();
      try{
        const r=await fetch(endpoint+'?name=example.com&type=TXT',{headers:{Accept:'application/dns-json'},cache:'no-store',signal:AbortSignal.timeout(15000)});
        const data=await r.json();
        rows.push({endpoint,http:r.status,dnsStatus:data.Status,answerCount:data.Answer?.length,ms:performance.now()-started});
      }catch(e){rows.push({endpoint,error:e.message,ms:performance.now()-started})}
    }
    return rows;
  });
  await page.getByRole('button',{name:'Load from DNS',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('#go').disabled,{},{timeout:30000});
  const result={at:new Date().toISOString(),mode:'live Chromium over configured HTTPS proxy; no interception',publicQueries:rows,appStatus:await page.locator('#status').textContent(),appTrace:JSON.parse(await page.locator('#trace').textContent())};
  fs.writeFileSync('evidence/live-browser.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
  await browser.close();server.close();
})().catch(e=>{console.error(e);process.exit(1)});
