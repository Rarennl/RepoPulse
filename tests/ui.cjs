// DOM integration test. Synthetic rows test rendering only, never SourceCraft facts.
// npm install --prefix /tmp/rh-ui jsdom@26.1.0
// NODE_PATH=/tmp/rh-ui/node_modules node tests/ui.cjs
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const html=fs.readFileSync(path.join(__dirname,'../app/static/index.html'),'utf8');
const source=fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8');
const wait=()=>new Promise(r=>setTimeout(r,30));
(async()=>{
 const dom=new JSDOM(html,{url:'http://localhost:8000/',runScripts:'outside-only'});
 const w=dom.window;let calls=0;
 w.fetch=async url=>{
  // A hung login request must not prevent catalogue rendering.
  if(url==='/api/me')return new Promise(()=>{});
  assert.match(url,/partial=true/);calls++;
  return {ok:true,status:200,json:async()=>({total:50,configured:true,items:Array.from({length:50},(_,i)=>({id:String(i),slug:'test/repo-'+i,score:50,coverage:50,eligible:false,likes:0}))})};
 };
 w.eval(source);await wait();
 assert.equal(w.document.getElementById('count').textContent,'50');
 assert.equal(w.document.querySelectorAll('#leaderboard tr').length,50);
 assert.equal(typeof w.RepoHealth.loadRank,'function');
 w.document.getElementById('refresh').click();await wait();assert.equal(calls,2);
 // An error is visible and is never rendered as an empty successful leaderboard.
 w.fetch=async()=>{throw Error('offline')};
 await w.RepoHealth.loadRank();
 assert.equal(w.document.getElementById('count').textContent,'Ошибка загрузки');
 assert.equal(w.document.getElementById('notice').textContent,'offline');
 assert.equal(w.document.getElementById('loading-help').classList.contains('hidden'),false);
 dom.window.close();console.log('UI integration OK: 50 rows, refresh, login isolation, explicit error/fallback.');
})().catch(e=>{console.error(e);process.exit(1)});
