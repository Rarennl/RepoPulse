(function () {
'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let user={authenticated:false},offset=0,active='rank',poll=null;
const date=s=>s?new Date(typeof s==='number'?s*1000:s).toLocaleDateString('ru-RU'):'Нет данных';
const num=s=>s===null||s===undefined?'Нет данных':Number(s).toLocaleString('ru-RU',{maximumFractionDigits:1});
function notify(text){$('notice').textContent=text;$('notice').classList.toggle('hidden',!text)}
const errors={sourcecraft_token_required:'Подключите токен SourceCraft для доступа к репозиториям.',
 yandex_oauth_not_configured:'Для входа нужно настроить OAuth-приложение Я ID на сервере.',
 unauthorized:'SourceCraft отклонил токен. Проверьте его срок действия.',forbidden:'Недостаточно прав в SourceCraft.',
 login_required:'Войдите через Я ID.',not_found:'Репозиторий или отчёт недоступен.',csrf_failed:'Сессия изменилась. Обновите страницу.',
 try_again_in_10_seconds:'Повторный запуск доступен через 10 секунд.',invalid_slug:'Укажите organization/repository.'};
async function api(path,options={}){
 const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),90000);
 try {
 const r=await fetch(path,{...options,signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRF-Token':user.csrf||'',...options.headers}});
 if(r.status===204)return null;
 const data=await r.json();if(!r.ok)throw Error(errors[data.detail]||'Не удалось выполнить запрос: '+(typeof data.detail==='string'?data.detail:r.status));return data;
 } catch(e) {if(e.name==='AbortError')throw Error('Источник отвечает слишком долго. Повторите загрузку.');throw e;} finally {clearTimeout(timeout);}
}
function show(view){active=view;for(const id of ['rank','mine','method','detail'])$(id).classList.toggle('hidden',id!==view);
 for(const id of ['rank','mine','method'])$('nav-'+id).classList.toggle('active',id===view);notify('');}
function link(f){try{const u=new URL(f.url);if(u.protocol==='https:'&&['sourcecraft.dev','api.sourcecraft.tech'].includes(u.hostname))return `<a href="${esc(u.href)}" target="_blank" rel="noopener">${esc(f.label)} ↗</a>`;}catch{}return esc(f.label);}
function facts(items){return `<ul class="facts">${items.map(f=>`<li>${link(f)}</li>`).join('')}</ul>`;}
async function loadRank(){
 if($('refresh').disabled)return;
 $('refresh').disabled=true;
 $('count').textContent='Загрузка…';
 try{const q=new URLSearchParams({language:$('language').value,sort:$('sort').value,partial:$('partial').checked,offset,limit:50});
 const data=await api('/api/leaderboard?'+q);$('count').textContent=data.total;$('empty').classList.toggle('hidden',!!data.items.length);
 $('leaderboard').innerHTML=data.items.map((r,i)=>`<tr><td>${offset+i+1}</td><td><a href="?repo=${esc(r.id)}" data-repo="${esc(r.id)}">${esc(r.slug)}</a><small>${r.eligible?'Подтверждённая оценка':'Предварительная оценка'} · покрытие ${num(r.coverage)}%</small></td><td><span class="score-chip ${r.score!==null&&r.score<50?'low':''}">${num(r.score)}</span></td><td>${num(r.likes)}</td><td>${esc(r.language||'Нет данных')}</td><td>${date(r.last_activity)}</td></tr>`).join('');
 $('page').textContent=Math.floor(offset/50)+1;$('prev').disabled=offset===0;$('next').disabled=offset+50>=data.total;
 if(!data.configured)notify('Сбор ещё не подключён: на сервере нужен токен SourceCraft. Демо-оценки в рейтинг не добавляются.');
 $('loading-help').classList.add('hidden');
 }catch(e){$('count').textContent='Ошибка загрузки';notify(e.message);$('loading-help').classList.remove('hidden');}finally{$('refresh').disabled=false}
}
async function loadUser(){try{user=await api('/api/me');$('login').classList.toggle('hidden',user.authenticated);$('logout').classList.toggle('hidden',!user.authenticated);
 $('need-login').classList.toggle('hidden',user.authenticated);$('account-panel').classList.toggle('hidden',!user.authenticated);
 $('connected').textContent=user.connected?'Токен подключён и хранится в зашифрованном виде.':'Токен ещё не подключён.';
 }catch(e){notify('Не удалось проверить сессию. Проверьте доступность сервиса.')}}
function renderResult(r){
 const score=num(r.score);
 return `<div class="result-top"><div class="score-panel"><div class="small">REPO HEALTH SCORE</div><div class="big-score">${r.score===null?'—':score}</div><div>из 100</div><p>Покрытие ${num(r.coverage)}%</p><span class="pill">${r.rank_eligible?'Подтверждённая оценка':'Предварительная оценка'}</span><p class="small">Анализ: ${date(r.analyzed_at)}<br>Методика ${esc(r.methodology)}</p></div><div class="category-grid">${r.categories.map(c=>`<a class="category" href="#category-${esc(c.id)}"><h3>${esc(c.name)}</h3><strong class="${c.score===null?'missing':''}">${num(c.score)}</strong><small>Вес ${c.weight}% · покрытие ${num(c.coverage)}%</small><div class="bar"><i data-width="${c.score||0}"></i></div></a>`).join('')}</div></div>
 <div class="two-col"><div class="panel"><h2>Сильные стороны</h2><p>${r.strengths.map(esc).join(' · ')||'Пока недостаточно подтверждённых результатов.'}</p></div><div class="panel"><h2>Требуют внимания</h2><p>${r.weaknesses.map(esc).join(' · ')||'Низкие оценки не выявлены. Проверьте покрытие данных.'}</p></div></div>
 <div class="panel"><h2>Что улучшить в первую очередь</h2>${r.recommendations.length?r.recommendations.map(x=>`<article class="recommendation"><h3><span class="priority">${esc(x.priority)}</span>${esc(x.problem)}</h3><p>${esc(x.why)}</p><div>${esc(x.action)}</div>${facts(x.facts)}<span class="pill">До +${num(x.delta_score)} Score · ${esc(x.category)}</span><p class="small">${esc(x.impact_note)}</p></article>`).join(''):'<p>Нет рекомендаций, подтверждённых доступными фактами. Это не означает отсутствия проблем.</p>'}</div>
 <div class="panel"><h2>Как рассчитана оценка</h2>${r.categories.map(c=>`<details id="category-${esc(c.id)}"><summary>${esc(c.name)} · ${num(c.score)}</summary>${c.metrics.map(m=>`<div class="metric"><div class="heading"><b>${esc(m.title)}</b><span>${num(m.score)}${m.score===null?'':' / 100'}</span></div><p>Значение: ${m.value===null?'Нет данных':esc(m.value)} · вес внутри категории: ${m.weight}%</p>${m.note?`<p>${esc(m.note)}</p>`:''}${facts(m.facts)}</div>`).join('')}</details>`).join('')}<p class="small">SHA-256 входов: ${esc(r.input_sha256)}</p></div>
 <div class="panel"><h2>Доступность источников</h2>${Object.entries(r.diagnostics||{}).map(([k,v])=>`<div class="metric"><b>${esc(k)}</b> · ${esc(v.status)}<p>${esc(v.reason||JSON.stringify(v))}</p></div>`).join('')}</div>`;
}
async function openRepo(id){show('detail');$('repo-name').textContent='Загрузка отчёта…';$('analysis-content').innerHTML='';$('download').classList.add('hidden');
 try{const data=await api('/api/repositories/'+encodeURIComponent(id));$('repo-name').textContent=data.slug;$('repo-link').href='https://sourcecraft.dev/'+data.slug;
 if(data.result){$('analysis-content').innerHTML=renderResult(data.result)+`<div class="panel"><h2>История Score</h2><div class="history">${data.history.map(h=>`<span>${date(h.date)}<br><b>${num(h.score)}</b> · покрытие ${num(h.coverage)}%</span>`).join('')}</div></div>`;
 $('download').href='/api/repositories/'+encodeURIComponent(id)+'/report.md';$('download').classList.remove('hidden');
 document.querySelectorAll('[data-width]').forEach(e=>e.style.width=Math.max(0,Math.min(100,Number(e.dataset.width)))+'%');
 }else{$('analysis-content').innerHTML='<div class="panel"><h2>Анализ ещё не завершён</h2><p>Статус: '+esc(data.last_job?.state||'не запущен')+'</p></div>';}
 history.replaceState(null,'','?repo='+encodeURIComponent(id));
 }catch(e){$('repo-name').textContent='Отчёт недоступен';notify(e.message)}}
async function pollJob(id){if(poll)clearTimeout(poll);try{const job=await api('/api/jobs/'+encodeURIComponent(id));$('job').classList.remove('hidden');$('job').textContent='Анализ: '+({queued:'в очереди',running:'сбор данных',succeeded:'завершён',failed:'не выполнен'}[job.state]||job.state)+(job.error?' · '+job.error:'');
 if(job.state==='succeeded'){await openRepo(job.repo_id);return;}if(job.state!=='failed')poll=setTimeout(()=>pollJob(id),3000);
 }catch(e){notify(e.message)}}
for(const id of ['rank','mine','method'])$('nav-'+id).onclick=()=>{show(id);history.replaceState(null,'','?view='+id);if(id==='rank')loadRank();if(id==='mine')loadUser();};
$('back').onclick=()=>{show('rank');history.replaceState(null,'','/');loadRank()};
$('leaderboard').onclick=e=>{const a=e.target.closest('[data-repo]');if(a){e.preventDefault();openRepo(a.dataset.repo)}};
$('refresh').onclick=()=>{offset=0;loadRank()};for(const id of ['language','sort','partial'])$(id).onchange=()=>{offset=0;loadRank()};
$('prev').onclick=()=>{offset=Math.max(0,offset-50);loadRank()};$('next').onclick=()=>{offset+=50;loadRank()};
$('token-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/me/sourcecraft',{method:'POST',body:JSON.stringify({token:$('token').value})});$('token').value='';await loadUser();notify('SourceCraft подключён.')}catch(x){notify(x.message)}};
$('disconnect').onclick=async()=>{try{await api('/api/me/sourcecraft',{method:'DELETE'});await loadUser()}catch(e){notify(e.message)}};
$('org-form').onsubmit=async e=>{e.preventDefault();try{const data=await api('/api/me/repositories?org='+encodeURIComponent($('org').value));$('repo-picker').innerHTML=data.items.map(r=>`<button data-slug="${esc(r.slug)}">${esc(r.slug)} · ${esc(r.visibility)}</button>`).join('')||'<p>Доступных репозиториев нет.</p>'}catch(x){notify(x.message)}};
$('repo-picker').onclick=e=>{if(e.target.dataset.slug)$('slug').value=e.target.dataset.slug};
$('analyze-form').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const j=await api('/api/analyses',{method:'POST',body:JSON.stringify({slug:$('slug').value})});await pollJob(j.job_id)}catch(x){notify(x.message)}finally{b.disabled=false}};
$('logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});location.href='/'}catch(e){notify(e.message)}};
$('weights').innerHTML=[['Security',20],['Состояние кода',20],['Документация',15],['CI/CD',15],['Активность',15],['Issues',15]].map(([n,w])=>`<div class="bar-row"><span>${n}</span><progress max="20" value="${w}"></progress><b>${w}%</b></div>`).join('');
// Login service must not block the public catalogue. Avoid page-global lexical names.
window.RepoHealth={loadRank,version:'2.0.0'};
$('partial').checked=new URLSearchParams(location.search).get('partial')!=='false';
(async()=>{const p=new URLSearchParams(location.search);loadUser();if(p.has('repo'))await openRepo(p.get('repo'));else{const v=['mine','method'].includes(p.get('view'))?p.get('view'):'rank';show(v);if(v==='rank')await loadRank()}})().catch(e=>notify(e.message));
})();
