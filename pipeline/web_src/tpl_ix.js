/* ---------- 탭: 지수차트 (코스피·코스닥 일봉 / 분봉 / 월봉, 거래대금, RSI) ----------
   data/ix/d.txt   : gzip+base64 JSON {"k":[[YYYYMMDD,시,고,저,종,거래대금(억원)],…],"q":[…]}  (2016-01-04~)
   data/ix/meta.json: {"minute_days":["YYYY-MM-DD",…],"vk":"a"|"v","note":"…"}
   data/ix/m/YYYY-MM-DD.txt : gzip+base64 JSON {"k":{t0,d,c,o,h,l,v,s,vk},"q":{…}}  (1분봉, 값은 s배 정수) */
window.tabIx=(()=>{
const E=id=>document.getElementById('ix-'+id);
let DAILY=null,META=null,inited=false;
const ST={mkt:'k',kind:'d',from:'',to:''};
const MD={};
const pad=n=>String(n).padStart(2,'0');
const iso=n=>`${String(n).slice(0,4)}-${String(n).slice(4,6)}-${String(n).slice(6,8)}`;
const addMonths=(d,n)=>{const t=new Date(d+'T00:00:00');t.setMonth(t.getMonth()-n);return t.getFullYear()+'-'+pad(t.getMonth()+1)+'-'+pad(t.getDate())};
const px=v=>v.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
const vfm=v=>v>=100?fmt(v):v>=10?f1(v):v.toLocaleString('ko-KR',{maximumFractionDigits:2});
/* RSI(14, Wilder). 값이 부족한 앞부분은 null */
function rsi(cl,n=14){const out=new Array(cl.length).fill(null);if(cl.length<=n)return out;
  let g=0,l=0;for(let i=1;i<=n;i++){const d=cl[i]-cl[i-1];if(d>=0)g+=d;else l-=d}g/=n;l/=n;
  out[n]=l===0?100:100-100/(1+g/l);
  for(let i=n+1;i<cl.length;i++){const d=cl[i]-cl[i-1];g=(g*(n-1)+(d>0?d:0))/n;l=(l*(n-1)+(d<0?-d:0))/n;out[i]=l===0?100:100-100/(1+g/l)}
  return out}
/* 거래대금 단위: 기본 천억원, 너무 작거나 크면 조정 (입력은 억원) */
const MONEY=[['조원','조',1e4],['천억원','천억',1e3],['백억원','백억',1e2],['억원','억',1]];
function moneyUnit(vmax){if(vmax/1e3>=1000)return MONEY[0];if(vmax/1e3>=1)return MONEY[1];if(vmax/1e2>=1)return MONEY[2];return MONEY[3]}
const SHARE=[['억주','억주',1e8],['천만주','천만주',1e7],['만주','만주',1e4],['주','주',1]];
function shareUnit(vmax){return SHARE.find(u=>vmax/u[2]>=10)||SHARE[3]}
async function loadDaily(){if(!DAILY){const [d,m]=await Promise.all([ldz('data/ix/d.txt'),ld('data/ix/meta.json').catch(()=>({minute_days:[]}))]);DAILY=d;META=m}return DAILY}
const minDay=T=>{if(!(T in MD))MD[T]=ldz(`data/ix/m/${T}.txt`).catch(()=>null);return MD[T]};
function decodeMin(u){const s=u.s||1,out=[];let t=u.t0,c=u.c[0];
  for(let i=0;i<u.c.length;i++){if(i){t+=u.d[i-1];c+=u.c[i]}out.push({t,o:(c+u.o[i])/s,h:(c+u.h[i])/s,l:(c-u.l[i])/s,c:c/s,v:u.v[i]})}return out}
function aggregate(bars,n){const g=new Map();
  bars.forEach(b=>{const k=Math.floor((b.t-540)/n);let a=g.get(k);
    if(!a)g.set(k,{t:540+k*n,o:b.o,h:b.h,l:b.l,c:b.c,v:b.v});else{a.h=Math.max(a.h,b.h);a.l=Math.min(a.l,b.l);a.c=b.c;a.v+=b.v}});
  return [...g.values()].sort((x,y)=>x.t-y.t)}
const hhmm=m=>pad(Math.floor(m/60))+':'+pad(m%60);
const MAXBARS=3000;
function setRange(months){const days=DAILY[ST.mkt];const mx=iso(days[days.length-1][0]),mn='2016-01-01';
  E('to').value=mx;const f=months===0?mn:addMonths(mx,months);E('from').value=f<mn?mn:f;ST.from=E('from').value;ST.to=mx}
function show(msg){E('cm').replaceChildren();E('cm')._shell=0;E('info').textContent=msg}
async function paint(){
  const host=E('cm');
  try{
    await loadDaily();
    const key=ST.mkt,nm=key==='k'?'코스피':'코스닥';
    const f=E('from').value||'2016-01-01',t=E('to').value||'9999-12-31';
    if(f>t)return show('시작일이 종료일보다 늦습니다.');
    const days=DAILY[key];
    let rows,cl,vals,xl,tl,vk='a',unitMsg,notes=[];
    if(ST.kind==='d'||ST.kind==='m'){
      let arr=days.map(r=>({d:r[0],o:r[1],h:r[2],l:r[3],c:r[4],v:r[5]}));
      if(ST.kind==='m'){const g=new Map();arr.forEach(r=>{const k=Math.floor(r.d/100);const a=g.get(k);
        if(!a)g.set(k,{d:k,o:r.o,h:r.h,l:r.l,c:r.c,v:r.v});else{a.h=Math.max(a.h,r.h);a.l=Math.min(a.l,r.l);a.c=r.c;a.v+=r.v}});arr=[...g.values()]}
      const rs=rsi(arr.map(r=>r.c));
      const f0=ST.kind==='m'?+f.slice(0,4)*100+ +f.slice(5,7):+f.replace(/-/g,''),t0=ST.kind==='m'?+t.slice(0,4)*100+ +t.slice(5,7):+t.replace(/-/g,'');
      const idx=[];arr.forEach((r,i)=>{if(r.d>=f0&&r.d<=t0)idx.push(i)});
      if(!idx.length)return show('이 기간에는 자료가 없습니다.');
      const sel=idx.map(i=>arr[i]);
      rows=sel.map((r,i)=>[i,r.o,r.h,r.l,r.c,r.v]);cl=idx.map(i=>rs[i]);
      const mon=ST.kind==='m';
      xl=r=>{const s=String(sel[r[0]].d);return mon?s.slice(2,4)+'.'+s.slice(4,6):s.slice(2,4)+'.'+s.slice(4,6)+'.'+s.slice(6,8)};
      tl=r=>{const s=String(sel[r[0]].d);return mon?s.slice(0,4)+'-'+s.slice(4,6):iso(sel[r[0]].d)};
    }else{
      const all=(META.minute_days||[]).filter(d=>d>=f&&d<=t);
      if(!all.length)return show(META.minute_days&&META.minute_days.length?`이 기간에는 분봉이 없습니다. 분봉은 ${META.minute_days[0]} ~ ${META.minute_days[META.minute_days.length-1]} 사이만 있습니다.`:'분봉 자료가 아직 없습니다.');
      const n=+E('mint').value,per=Math.ceil(390/n),maxd=Math.max(1,Math.floor(MAXBARS/per));
      const use=all.slice(-maxd);if(use.length<all.length)notes.push(`기간이 길어 최근 ${use.length}거래일만 보여 드립니다. (${n}분봉 ${MAXBARS.toLocaleString('ko-KR')}개 이내)`);
      E('info').textContent='불러오는 중…';
      const files=await Promise.all(use.map(minDay));
      const bars=[];files.forEach((fd,i)=>{if(!fd||!fd[key])return;const u=fd[key];vk=u.vk||'v';aggregate(decodeMin(u),n).forEach(b=>bars.push({...b,date:use[i]}))});
      if(!bars.length)return show('이 기간의 분봉을 불러오지 못했습니다.');
      const rs=rsi(bars.map(b=>b.c));
      rows=bars.map((b,i)=>[i,b.o,b.h,b.l,b.c,vk==='a'?b.v/100:b.v]);cl=rs;
      xl=r=>{const b=bars[r[0]];return b.date.slice(5).replace('-','.')+' '+hhmm(b.t)};
      tl=r=>{const b=bars[r[0]];return b.date+' '+hhmm(b.t)};
    }
    const vmax=Math.max(...rows.map(r=>r[5]));
    let U,label;
    if(vk==='a'){U=moneyUnit(vmax);label='거래대금'}else{U=shareUnit(vmax);label='거래량'}
    rows.forEach(r=>{r[5]=r[5]/U[2]});
    const first=rows[0][4],lastd=rows[rows.length-1];
    E('info').textContent=`${nm} ${ST.kind==='d'?'일봉':ST.kind==='m'?'월봉':E('mint').value+'분봉'} · ${rows.length.toLocaleString('ko-KR')}개 · 아래 막대: ${label}(${U[0]}), 그 아래: RSI(14)`+(notes.length?' · '+notes.join(' '):'');
    mountChart(host,rows,{key:`ix|${key}|${ST.kind}|${E('mint').value}|${f}|${t}`,xl,tl,vu:U[1],vf:vfm,vl:label,pf:px,rsi:cl,
      ref:{p:first,t:'기간 시작 종가 대비'},label:nm+' 지수 차트'});
  }catch(e){show('지수 자료를 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.')}
}
function init(){
  inited=true;
  E('mkt').onchange=()=>{ST.mkt=E('mkt').value;paint()};
  document.querySelectorAll('#p-ix [data-ik]').forEach(b=>b.onclick=()=>{ST.kind=b.dataset.ik;
    document.querySelectorAll('#p-ix [data-ik]').forEach(x=>x.setAttribute('aria-pressed',x===b));E('mintw').hidden=ST.kind!=='min';
    if(ST.kind==='min'&&META&&META.minute_days&&META.minute_days.length){const md=META.minute_days,last=md[md.length-1];
      /* 분봉은 며칠치만 보면 되므로, 기간이 너무 길면 최근 1개월로 줄여 줍니다 */
      if(E('from').value<addMonths(last,1)){E('from').value=addMonths(last,1);E('to').value=last}}
    paint()});
  E('mint').onchange=paint;E('from').onchange=paint;E('to').onchange=paint;
  document.querySelectorAll('#p-ix [data-ir]').forEach(b=>b.onclick=()=>{setRange(+b.dataset.ir);paint()});
}
return async function(){
  if(!inited)init();
  try{await loadDaily()}catch(e){return show('지수 자료가 아직 없습니다. (자료가 만들어지면 표시됩니다)')}
  if(!E('from').value||!E('to').value)setRange(12);
  paint();
}})();
