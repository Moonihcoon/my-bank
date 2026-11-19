/* ---------- 탭: 리서치 (네이버 증권 국내종목 리서치, 기간 설정 + 종목 검색) ----------
   data/rs/index.json 의 날짜 목록과 data/rs/YYYY-MM.json 의 월별 리포트를 읽습니다.
   항목: [번호, 종목코드, 종목명, 증권사, 게시일, 제목, 의견(원문), 의견, 목표주가, 전일 종가, 요약] */
window.tabRs=(()=>{
const WD=['일','월','화','수','목','금','토'];
const E=id=>document.getElementById('rr-'+id);
const PAGE=100;
let IDX=null,MON={},inited=false,SHOWN=PAGE;
const month=async ym=>{if(!(ym in MON))MON[ym]=ld(`data/rs/${ym}.json`).catch(()=>[]);return MON[ym]};
const wd=d=>WD[new Date(d+'T00:00:00').getDay()];
const opCls=o=>o==='매수'?'b':o==='매도'?'s':'';
const addDays=(d,n)=>{const t=new Date(d+'T00:00:00');t.setDate(t.getDate()+n);return t.getFullYear()+'-'+String(t.getMonth()+1).padStart(2,'0')+'-'+String(t.getDate()).padStart(2,'0')};
const monthsIn=(a,b)=>{const out=[];let y=+a.slice(0,4),m=+a.slice(5,7);const ye=+b.slice(0,4),me=+b.slice(5,7);
  while(y<ye||(y===ye&&m<=me)){out.push(y+'-'+String(m).padStart(2,'0'));if(++m>12){m=1;y++}}return out};
function setRange(days){
  const mx=IDX.dates[0][0],mn=IDX.dates[IDX.dates.length-1][0];
  E('to').value=mx;E('from').value=days===0?mn:days===1?mx:(a=>a<mn?mn:a)(addDays(mx,-(days-1)));
}
/* ---------- 차트(일봉 / 3분 · 5분 · 20분봉) ---------- */
const TF=[['d','일봉'],['3','3분'],['5','5분'],['20','20분']];
const hhmm=m=>String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0');
const nextWeekday=d=>{const t=new Date(d+'T00:00:00');while(t.getDay()%6===0)t.setDate(t.getDate()+1);return t.getFullYear()+'-'+String(t.getMonth()+1).padStart(2,'0')+'-'+String(t.getDate()).padStart(2,'0')};
const MN={};
const minDay=T=>{if(!(T in MN))MN[T]=ldz(`data/mn/${T}.txt`).catch(()=>null);return MN[T]};
function decodeMin(u){const out=[];let t=u.t0,c=u.c[0];
  for(let i=0;i<u.c.length;i++){if(i){t+=u.d[i-1];c+=u.c[i]}out.push({t,o:c+u.o[i],h:c+u.h[i],l:c-u.l[i],c,v:u.v[i]})}return out}
function aggregate(bars,n){const g=new Map();
  bars.forEach(b=>{const k=Math.floor((b.t-540)/n);let a=g.get(k);
    if(!a)g.set(k,{t:540+k*n,o:b.o,h:b.h,l:b.l,c:b.c,v:b.v});else{a.h=Math.max(a.h,b.h);a.l=Math.min(a.l,b.l);a.c=b.c;a.v+=b.v}});
  return [...g.values()].sort((x,y)=>x.t-y.t)}
let TCODE=null;
async function tickIdx(code){await loadTick();if(!TCODE){TCODE={};TICK.forEach((t,i)=>TCODE[t[0]]=i)}return TCODE[code]}
async function openChart(rec,host){
  const [id,code,name,,date,,,,,prev]=rec;
  if(!host._ready){
    host._ready=1;host._tf='d';
    host.innerHTML=`<div class="rs-chh"><b></b><div class="rs-tf" role="group" aria-label="차트 종류">${TF.map(([k,l])=>`<button type="button" data-tf="${k}" aria-pressed="${k==='d'}">${l}</button>`).join('')}</div><span class="rs-chn"></span></div><div class="rs-cm"></div>`;
    host.querySelectorAll('[data-tf]').forEach(b=>b.onclick=()=>{host._tf=b.dataset.tf;host.querySelectorAll('[data-tf]').forEach(x=>x.setAttribute('aria-pressed',x===b));paint(rec,host)});
  }
  await paint(rec,host);
}
async function paint(rec,host){
  const [id,code,name,broker,date,title,,,goal,prev]=rec,tf=host._tf,box=host.querySelector('.rs-cm'),ttl=host.querySelector('b'),note=host.querySelector('.rs-chn');
  const setMsg=m=>{box.replaceChildren();box._shell=0;note.textContent=m};
  ttl.textContent=name+' '+(tf==='d'?'일봉':tf+'분봉');note.textContent='불러오는 중…';
  try{
    const ti=await tickIdx(code);
    if(ti==null)return setMsg('이 종목은 차트 자료가 없습니다.');
    let idx=DATES.findIndex(d=>d>=date);const inData=idx>=0;
    if(tf==='d'){
      if(!inData)idx=DATES.length-1;
      const rows=await stockRows(ti,Math.max(0,idx-120),Math.min(DATES.length-1,idx+20));
      if(!rows.length)return setMsg('이 종목의 일봉 자료가 없습니다.');
      const rp=rows.find(x=>x[0]===idx);
      ttl.textContent=`${name} 일봉 · 게시일 ${date}`;
      note.textContent=inData?(DATES[idx]!==date?`게시일(${date})은 휴장일이라 다음 거래일(${DATES[idx]})에 표시합니다. `:'')+'아래 막대는 거래대금(억원)':'게시일 시세가 아직 없어 가장 최근 일봉까지 보여 드립니다.';
      mountChart(box,rows,{key:'rs'+code+'_'+idx+'_d',marks:inData?[{di:idx,t:'게시일'}]:[],ref:{p:prev||(rp?rp[4]:rows[rows.length-1][4]),t:'게시 전일 종가 대비'},label:name+' 일봉'});
      return;
    }
    const T=inData?DATES[idx]:nextWeekday(date);
    const day=await minDay(T);
    const u=day&&day[code];
    if(!u)return setMsg(`${T} ${name}의 분봉이 없습니다. (분봉은 최근 1년치만 받을 수 있고, 수집이 끝난 날짜부터 표시됩니다.)`);
    const bars=aggregate(decodeMin(u),+tf);
    const tms=bars.map(b=>b.t);
    const rows=bars.map((b,i)=>[i,b.o,b.h,b.l,b.c,b.c*b.v/1e6]);
    let pc=null;
    if(inData&&idx>0){const dr=await stockRows(ti,Math.max(0,idx-5),idx-1);if(dr.length)pc=dr[dr.length-1][4]}
    ttl.textContent=`${name} ${tf}분봉 · ${T}`;
    note.textContent=(T!==date?`게시일(${date})이 휴장일이라 다음 거래일 기준 · `:'게시일 기준 · ')+'아래 막대는 거래대금(백만원)';
    mountChart(box,rows,{key:'rs'+code+'_'+T+'_'+tf,ref:pc?{p:pc,t:'전일 종가 대비'}:{p:rows[0][1],t:'시가 대비'},label:`${name} ${tf}분봉`,
      xl:r=>hhmm(tms[r[0]]),tl:r=>`${T} ${hhmm(tms[r[0]])}`,vu:'백만'});
  }catch(e){setMsg('차트를 불러오지 못했습니다. 잠시 뒤 다시 눌러 주세요.')}
}
async function render(reset){
  if(reset)SHOWN=PAGE;
  let from=E('from').value,to=E('to').value;
  if(!from||!to)return;
  if(from>to){[from,to]=[to,from];E('from').value=from;E('to').value=to}
  const q=E('q').value.trim().toLowerCase(),op=E('op').value;
  const mons=await Promise.all(monthsIn(from,to).map(month));
  const all=[].concat(...mons).filter(r=>r[4]>=from&&r[4]<=to).sort((a,b)=>a[4]<b[4]?1:a[4]>b[4]?-1:b[0]-a[0]);
  const list=all.filter(r=>(!op||r[7]===op)&&(!q||r[2].toLowerCase().includes(q)||r[3].toLowerCase().includes(q)||String(r[1]).includes(q)));
  const cnt={매수:0,중립:0,매도:0,없음:0};list.forEach(r=>cnt[r[7]]=(cnt[r[7]]||0)+1);
  const days=new Set(list.map(r=>r[4])).size;
  const rng=from===to?`${from} (${wd(from)})`:`${from} ~ ${to}`;
  E('info').textContent=`${rng} · ${(q||op)?'조건에 맞는 ':''}리포트 ${list.length}건${from!==to?` (${days}일)`:''} · 매수 ${cnt.매수} · 중립 ${cnt.중립} · 매도 ${cnt.매도} · 의견 없음 ${cnt.없음}`;
  if(!list.length){E('list').innerHTML='<div class="rs-empty">표시할 리포트가 없습니다.</div>';E('more').hidden=true;return}
  const perDay={};list.forEach(r=>perDay[r[4]]=(perDay[r[4]]||0)+1);
  let last='';
  E('list').innerHTML=list.slice(0,SHOWN).map(r=>{
    const [id,code,name,broker,d,title,opRaw,opn,goal,prev,sum]=r;
    const up=goal&&prev?(goal/prev-1)*100:null;
    const upH=up==null?'':`<span class="${up>=0?'rs-up':'rs-dn'}">${pctTxt(up)}</span>`;
    const dh=d!==last?`<div class="rs-dh">${d} (${wd(d)}) · ${perDay[d]}건</div>`:'';last=d;
    return dh+`<div class="rs-it"><div class="rs-h"><span class="rs-nm">${esc(name)}<span class="rs-cd">${esc(code)}</span></span>`+
      `<span class="rs-kv">전일 종가 <b>${prev?fmt(prev):'–'}</b></span>`+
      `<span class="rs-kv">목표주가 <b>${goal?fmt(goal):'–'}</b>${upH}</span>`+
      `<span class="rs-op ${opCls(opn)}" title="${esc(opRaw||'투자의견 없음')}">${opn==='없음'?'의견 없음':esc(opn)}</span></div>`+
      `<div class="rs-meta"><b>${esc(broker)}</b> · ${esc(title)}</div>`+
      `<div class="rs-b"><div class="rs-sm${sum?'':' no'}">${sum?esc(sum):'요약이 없는 리포트입니다. 원문을 확인하세요.'}</div>`+
      `<div class="rs-act"><button type="button" class="rs-go" data-ch="${id}" aria-expanded="false">차트</button><a class="rs-go" href="https://stock.naver.com/research/company/${id}" target="_blank" rel="noopener noreferrer">원문</a></div></div>`+
      `<div class="rs-ch" id="rr-ch${id}" hidden></div></div>`}).join('');
  const byId={};list.forEach(r=>byId[r[0]]=r);
  E('list').querySelectorAll('[data-ch]').forEach(b=>b.onclick=()=>{
    const host=document.getElementById('rr-ch'+b.dataset.ch),open=host.hidden;
    host.hidden=!open;b.setAttribute('aria-expanded',open);
    if(open)openChart(byId[b.dataset.ch],host)});
  E('more').hidden=list.length<=SHOWN;
  E('more').textContent=`더 보기 (${list.length-SHOWN}건 남음)`;
}
return async function tabRs(){
  if(!inited){
    inited=true;
    try{IDX=await ld('data/rs/index.json')}catch(e){IDX=null}
    if(!IDX||!IDX.dates.length){E('info').textContent='아직 수집된 리서치가 없습니다. 자동 수집이 끝나면 표시됩니다.';return}
    const mx=IDX.dates[0][0],mn=IDX.dates[IDX.dates.length-1][0];
    ['from','to'].forEach(k=>{E(k).min=mn;E(k).max=mx;E(k).onchange=()=>render(true)});
    setRange(1);
    E('op').onchange=()=>render(true);E('q').oninput=()=>render(true);
    document.querySelectorAll('#p-research [data-rg]').forEach(b=>b.onclick=()=>{setRange(+b.dataset.rg);render(true)});
    E('more').onclick=()=>{SHOWN+=PAGE;render(false)};
  }
  if(IDX&&IDX.dates.length)await render(false);
}})();
