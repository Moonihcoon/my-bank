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
      `<a class="rs-go" href="https://stock.naver.com/research/company/${id}" target="_blank" rel="noopener noreferrer">원문</a></div></div>`}).join('');
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
