/* ---------- 탭: 리서치 (네이버 증권 국내종목 리서치, 날짜별) ----------
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
async function render(reset){
  if(reset)SHOWN=PAGE;
  const date=E('dt').value;
  if(!date){return}
  const q=E('q').value.trim().toLowerCase(),op=E('op').value;
  const all=(await month(date.slice(0,7))).filter(r=>r[4]===date);
  const list=all.filter(r=>(!op||r[7]===op)&&(!q||r[2].toLowerCase().includes(q)||r[3].toLowerCase().includes(q)||String(r[1]).includes(q)));
  const cnt={매수:0,중립:0,매도:0,없음:0};all.forEach(r=>cnt[r[7]]=(cnt[r[7]]||0)+1);
  E('info').textContent=`${date} (${wd(date)}) · 리포트 ${all.length}건 · 매수 ${cnt.매수} · 중립 ${cnt.중립} · 매도 ${cnt.매도} · 의견 없음 ${cnt.없음}`+((q||op)?` — 조건에 맞는 ${list.length}건`:'');
  const i=IDX.dates.findIndex(x=>x[0]===date);
  E('prev').disabled=i>=IDX.dates.length-1;E('next').disabled=i<=0;
  if(!list.length){E('list').innerHTML='<div class="rs-empty">표시할 리포트가 없습니다.</div>';E('more').hidden=true;return}
  E('list').innerHTML=list.slice(0,SHOWN).map(r=>{
    const [id,code,name,broker,d,title,opRaw,opn,goal,prev,sum]=r;
    const up=goal&&prev?(goal/prev-1)*100:null;
    const upH=up==null?'':`<span class="${up>=0?'rs-up':'rs-dn'}">${pctTxt(up)}</span>`;
    return `<div class="rs-it"><div class="rs-h"><span class="rs-nm">${esc(name)}<span class="rs-cd">${esc(code)}</span></span>`+
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
    if(!IDX||!IDX.dates.length){E('info').textContent='아직 수집된 리서치가 없습니다. 자동 수집이 끝나면 표시됩니다.';E('dt').innerHTML='';return}
    E('dt').innerHTML=IDX.dates.map(([d,n])=>`<option value="${d}">${d} (${wd(d)}) · ${n}건</option>`).join('');
    E('dt').onchange=()=>render(true);E('op').onchange=()=>render(true);E('q').oninput=()=>render(true);
    E('prev').onclick=()=>{const s=E('dt');if(s.selectedIndex<s.options.length-1){s.selectedIndex++;render(true)}};
    E('next').onclick=()=>{const s=E('dt');if(s.selectedIndex>0){s.selectedIndex--;render(true)}};
    E('more').onclick=()=>{SHOWN+=PAGE;render(false)};
  }
  if(IDX&&IDX.dates.length)await render(false);
}})();
