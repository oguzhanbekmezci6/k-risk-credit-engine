'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const API = '/api/v4';
let csrfToken = '';
let user = null;
let policies = [];
let historyRows = [];
let currentPage = 'overview';
let explanationsOn = false;
let helpMode = 'page';

const fmt = (n, d = 0) => Number(n ?? 0).toLocaleString('tr-TR', {minimumFractionDigits:d, maximumFractionDigits:d});
const pct = (n) => `%${fmt(Number(n ?? 0) * 100, 1)}`;
const money = (n) => { const v=Number(n ?? 0); const hasFraction=Math.abs(v-Math.round(v))>1e-9; return `${v.toLocaleString('tr-TR', {minimumFractionDigits:hasFraction?2:0, maximumFractionDigits:2})} TL`; };
const roleLabel = (v) => ({admin:'Yönetici', risk_manager:'Risk Yöneticisi', analyst:'Kredi Analisti'}[v] || String(v ?? ''));
const statusLabel = (v) => ({active:'Aktif', challenger:'Alternatif', draft:'Taslak', evaluation:'Değerlendirme'}[v] || String(v ?? '—'));
const stateName = (v) => ({baz:'Baz', yavaslama:'Yavaşlama', agir_stres:'Ağır stres'}[v] || String(v ?? '—'));
const columnHints={Tarih:'Kararın veya olayın oluşturulduğu zaman.',Başvuru:'Banka başvuru referansı.',Karar:'K-Risk tarafından önerilen veya geçerli nihai karar.',Limit:'Önerilen veya geçerli kredi tutarı.',Stres:'Kararın kötüleşen ekonomik koşullarda korunup korunmadığı.',Politika:'Kararı üreten risk politikası ve strateji seti.',İşlem:'Bu kayıt üzerinde kullanabileceğiniz eylemler.',Durum:'Politikanın veya kullanıcının mevcut çalışma durumu.','Maks. PD':'Politikanın kabul ettiği en yüksek temerrüt olasılığı.','Min. RAROC':'Politikanın kabul ettiği asgari risk-ayarlı getiri eşiği.','Beklenen zarar':'Riskin beklenen parasal maliyeti.','Onay oranı':'Toplam başvuruların ne kadarının onaylandığı.','ROC AUC':'Risk modelinin sıralama/ayırt etme gücü.','Ek K/Z':'Yeni politika ile geçmiş politika arasındaki ekonomik sonuç farkı.'};

function clear(el){ while(el && el.firstChild) el.removeChild(el.firstChild); }
function node(tag, cls='', text=''){
  const e=document.createElement(tag); if(cls)e.className=cls; if(text!=='')e.textContent=String(text); return e;
}
function add(parent,...children){ children.filter(Boolean).forEach(c=>parent.appendChild(c)); return parent; }
function small(text){ return node('small','',text); }
function chip(text, kind='warn'){ return node('span',`decision-chip ${kind}`,text); }
function metric(title,value,note='',valueClass=''){
  const box=node('div','metric'); add(box,node('span','',title),node('strong',valueClass,value),small(note)); return box;
}
function panel(title,subtitle=''){
  const p=node('article','panel');
  if(title){const h=node('div','panel-head'), l=node('div'); add(l,node('h3','',title),node('p','',subtitle)); add(h,l); p.appendChild(h);} return p;
}
function table(headers,rows){
  const wrap=node('div','table-wrap'), t=node('table'), thead=node('thead'), hr=node('tr');
  headers.forEach(h=>{const th=node('th','',h);if(columnHints[h]){th.title=columnHints[h];th.setAttribute('aria-label',`${h}. ${columnHints[h]}`);}hr.appendChild(th);}); thead.appendChild(hr);
  const tbody=node('tbody'); rows.forEach(cells=>{const tr=node('tr'); cells.forEach(cell=>{const td=node('td'); if(cell instanceof Node)td.appendChild(cell);else td.textContent=String(cell??'—');tr.appendChild(td);});tbody.appendChild(tr);});
  add(t,thead,tbody);wrap.appendChild(t);return wrap;
}
function formatDate(value){ try{return new Date(value).toLocaleString('tr-TR',{dateStyle:'short',timeStyle:'short'});}catch{return String(value??'—');} }
function decisionKind(v){ return v==='ONAY'||v==='TAM ONAY'?'good':v==='REDDET'?'bad':v==='KISMİ ONAY'?'warn':'neutral'; }
function decisionText(v){ return ['ONAY','TAM ONAY','KISMİ ONAY','REDDET'].includes(v)?v:String(v??'—'); }

function parseMoneyValue(value){
  const raw=String(value??'').trim().replace(/\s|TL|₺/gi,'');
  if(!raw)return 0;
  const parts=raw.split(',');
  const integerDigits=(parts.shift()||'').replace(/[^0-9]/g,'');
  const decimalDigits=parts.join('').replace(/[^0-9]/g,'').slice(0,2);
  if(!integerDigits && !decimalDigits)return 0;
  return Number(`${integerDigits||'0'}.${decimalDigits||'0'}`);
}
function formatMoneyInput(el){
  const raw=String(el.value??'').replace(/\s|TL|₺/gi,'');
  if(!raw){el.value='';return;}
  const hasComma=raw.includes(',');
  const parts=raw.split(',');
  const integerDigits=(parts.shift()||'').replace(/[^0-9]/g,'')||'0';
  const decimalDigits=parts.join('').replace(/[^0-9]/g,'').slice(0,2);
  const max=Number(el.dataset.max||1000000000);
  if(Number(integerDigits)>max){el.value=max.toLocaleString('tr-TR',{maximumFractionDigits:0});return;}
  const integerText=Number(integerDigits).toLocaleString('tr-TR',{maximumFractionDigits:0});
  el.value=hasComma?`${integerText},${decimalDigits}`:integerText;
}
function initMoneyInputs(){
  $$('.money-input').forEach(el=>{formatMoneyInput(el);el.addEventListener('input',()=>formatMoneyInput(el));el.addEventListener('blur',()=>{if(el.value.endsWith(','))el.value=el.value.slice(0,-1);formatMoneyInput(el);});});
}
function canDownloadReport(){return user?.role==='admin'||user?.role==='risk_manager';}
function reportButton(decisionId,label='Karar Raporunu İndir'){
  const a=node('a','btn primary report-download',label);a.href=`${API}/decision/${encodeURIComponent(decisionId)}/report.pdf`;a.setAttribute('download','');return a;
}

function readableApiError(data,status=0){
  if(!data) return status ? `İşlem tamamlanamadı (HTTP ${status}).` : 'Sunucuya ulaşılamadı.';
  const detail=data.detail;
  if(typeof detail==='string' && detail.trim()) return detail.trim();
  if(Array.isArray(detail)){
    const parts=detail.slice(0,5).map(item=>{
      if(typeof item==='string') return item;
      if(item && typeof item==='object'){
        const loc=Array.isArray(item.loc)?item.loc.filter(x=>!['body','query','path'].includes(String(x))):[];
        const field=loc.length?String(loc[loc.length-1]).replaceAll('_',' '):'Alan';
        const msg=typeof item.msg==='string'?item.msg:'Geçersiz değer.';
        return `${field}: ${msg.replace(/^Value error,\s*/,'')}`;
      }
      return String(item);
    }).filter(Boolean);
    if(parts.length) return parts.join(' ');
  }
  if(detail && typeof detail==='object'){
    if(typeof detail.message==='string') return detail.message;
    try{return JSON.stringify(detail);}catch(_){return 'Girilen bilgileri kontrol edin.';}
  }
  if(typeof data.message==='string') return data.message;
  return status ? `İşlem tamamlanamadı (HTTP ${status}).` : 'İşlem tamamlanamadı.';
}

async function api(path,opt={}){
  const headers={...(opt.headers||{})}, method=(opt.method||'GET').toUpperCase();
  if(opt.json!==undefined){headers['Content-Type']='application/json';opt.body=JSON.stringify(opt.json);}
  if(!['GET','HEAD','OPTIONS'].includes(method)&&csrfToken&&!path.endsWith('/auth/login')&&!path.endsWith('/auth/setup'))headers['X-CSRF-Token']=csrfToken;
  let r;
  try{r=await fetch(path,{...opt,method,headers,credentials:'same-origin',cache:'no-store'});}
  catch(_){throw new Error('K-Risk sunucusuna ulaşılamadı. Uygulamanın çalıştığını kontrol edip tekrar deneyin.');}
  let data=null;
  try{data=await r.json();}catch(_){data=null;}
  if(!r.ok)throw new Error(readableApiError(data,r.status));
  return data??{};
}

function showOnly(view){
  ['#authLoadingView','#setupView','#loginView','#passwordView','#appView'].forEach(s=>$(s)?.classList.add('hidden'));
  $(view)?.classList.remove('hidden');
}
function setButtonBusy(button,busy,busyText='İşleniyor…'){
  if(!button)return;
  if(busy){button.dataset.originalText=button.textContent;button.textContent=busyText;button.classList.add('loading');button.disabled=true;}
  else{button.textContent=button.dataset.originalText||button.textContent;button.classList.remove('loading');button.disabled=false;}
}
function setError(selector,message=''){
  const el=$(selector);if(!el)return;el.textContent=message;
}
function passwordProblem(pass){
  if(pass.length<12)return 'Şifre en az 12 karakter olmalıdır.';
  if(pass.length>128)return 'Şifre en fazla 128 karakter olabilir.';
  if(!/[a-zçğıöşü]/.test(pass))return 'Şifre en az bir küçük harf içermelidir.';
  if(!/[A-ZÇĞİÖŞÜ]/.test(pass))return 'Şifre en az bir büyük harf içermelidir.';
  if(!/[0-9]/.test(pass))return 'Şifre en az bir rakam içermelidir.';
  if(!/[^\p{L}\p{N}]/u.test(pass))return 'Şifre en az bir özel karakter içermelidir.';
  return '';
}
function usernameProblem(username){
  const u=String(username||'').trim();
  if(u.length<3)return 'Kullanıcı adı en az 3 karakter olmalıdır.';
  if(u.length>64)return 'Kullanıcı adı en fazla 64 karakter olabilir.';
  if(/\s/u.test(u))return 'Kullanıcı adında boşluk kullanılamaz.';
  if(!/^[\p{L}\p{N}._-]+$/u.test(u))return 'Kullanıcı adı yalnızca harf, rakam, nokta, alt çizgi veya tire içerebilir.';
  return '';
}
function applyRoleVisibility(){
  $$('.role-nav,.role-page,.role-control').forEach(el=>{const allowed=(el.dataset.roles||'').split(',');el.classList.toggle('hidden',!allowed.includes(user?.role));});
  $('#sessionUser').textContent=user?.username||'—';$('#sessionRole').textContent=roleLabel(user?.role);
}
function showApp(){showOnly('#appView');applyRoleVisibility();$('#welcomeTitle').textContent=`Hoş geldiniz, ${user?.username||''}.`;loadPolicies();loadOverview();loadHistory();if(user?.role!=='analyst')renderScienceMap();applyExplanationMode();applyActionHelp();}
function showPasswordChange(){showOnly('#passwordView');}
function showLogin(){csrfToken='';user=null;setError('#loginError');showOnly('#loginView');setTimeout(()=>$('#loginUser')?.focus(),50);}
function showSetup(state={}){
  csrfToken='';user=null;showOnly('#setupView');
  $('#setupCodeField').classList.toggle('hidden',!state.requires_setup_code);
  setError('#setupError',state.can_setup===false?'İlk kurulum bu ortamda kapalı. BT yöneticiniz kurulum kodunu tanımlamalıdır.':'');
  $('#setupBtn').disabled=state.can_setup===false;
  setTimeout(()=>$('#setupUser')?.focus(),50);
}
function showAuthLoading(message='Giriş durumu kontrol ediliyor…',retry=false){
  showOnly('#authLoadingView');$('#authLoadingText').textContent=message;$('#authRetryBtn').classList.toggle('hidden',!retry);$('.auth-spinner').classList.toggle('hidden',retry);
}

async function restoreSession(){
  showAuthLoading();
  try{
    const setup=await api(`${API}/auth/setup-status`);
    if(setup.needs_setup){showSetup(setup);return;}
    try{
      const r=await api(`${API}/auth/session`);user=r;csrfToken=r.csrf_token;
      if(r.must_change_password)showPasswordChange();else showApp();
    }catch(e){
      if(/sunucusuna ulaşılamadı/i.test(e.message))throw e;
      showLogin();
    }
  }catch(e){
    showAuthLoading(e.message||'Giriş sistemi başlatılamadı.',true);
  }
}

async function createFirstAccount(){
  const btn=$('#setupBtn'),username=$('#setupUser').value.trim(),pass=$('#setupPass').value,pass2=$('#setupPass2').value;
  setError('#setupError');
  const uErr=usernameProblem(username);if(uErr){setError('#setupError',uErr);$('#setupUser').focus();return;}
  const pErr=passwordProblem(pass);if(pErr){setError('#setupError',pErr);$('#setupPass').focus();return;}
  if(pass!==pass2){setError('#setupError','Şifreler birbiriyle aynı değil.');$('#setupPass2').focus();return;}
  setButtonBusy(btn,true,'Hesap oluşturuluyor…');
  try{
    const r=await api(`${API}/auth/setup`,{method:'POST',json:{username,password:pass,setup_code:$('#setupCode').value||null}});
    user=r;csrfToken=r.csrf_token;$('#setupPass').value='';$('#setupPass2').value='';$('#setupCode').value='';showApp();
  }catch(e){setError('#setupError',e.message);}
  finally{setButtonBusy(btn,false);}
}

async function login(){
  const btn=$('#loginBtn'),username=$('#loginUser').value.trim(),password=$('#loginPass').value;
  setError('#loginError');
  if(!username){setError('#loginError','Kullanıcı adınızı yazın.');$('#loginUser').focus();return;}
  if(!password){setError('#loginError','Şifrenizi yazın.');$('#loginPass').focus();return;}
  setButtonBusy(btn,true,'Giriş yapılıyor…');
  try{
    const r=await api(`${API}/auth/login`,{method:'POST',json:{username,password}});
    user=r;csrfToken=r.csrf_token;$('#loginPass').value='';
    if(r.must_change_password)showPasswordChange();else showApp();
  }catch(e){setError('#loginError',e.message);}
  finally{setButtonBusy(btn,false);}
}

$('#setupBtn').onclick=createFirstAccount;
$('#setupPass2').addEventListener('keydown',e=>{if(e.key==='Enter')createFirstAccount();});
$('#loginBtn').onclick=login;
$('#loginPass').addEventListener('keydown',e=>{if(e.key==='Enter')login();});
$('#authRetryBtn').onclick=restoreSession;
$('#loginHelpBtn').onclick=()=>$('#loginHelpBox').classList.toggle('hidden');
$$('.password-toggle').forEach(btn=>btn.onclick=()=>{const input=$(`#${btn.dataset.target}`);if(!input)return;const show=input.type==='password';input.type=show?'text':'password';btn.textContent=show?'Gizle':'Göster';btn.setAttribute('aria-label',show?'Şifreyi gizle':'Şifreyi göster');});

$('#changePasswordBtn').onclick=async()=>{
  const btn=$('#changePasswordBtn'),current=$('#currentPass').value,next=$('#newPass').value,next2=$('#newPass2').value;setError('#passwordError');
  const pErr=passwordProblem(next);if(pErr){setError('#passwordError',pErr);return;}
  if(next!==next2){setError('#passwordError','Yeni şifreler birbiriyle aynı değil.');return;}
  setButtonBusy(btn,true,'Şifre değiştiriliyor…');
  try{const r=await api(`${API}/auth/change-password`,{method:'POST',json:{current_password:current,new_password:next}});csrfToken=r.csrf_token;user.must_change_password=false;$('#currentPass').value='';$('#newPass').value='';$('#newPass2').value='';showApp();}
  catch(e){setError('#passwordError',e.message);}
  finally{setButtonBusy(btn,false);}
};
$('#logoutBtn').onclick=async()=>{try{await api(`${API}/auth/logout`,{method:'POST'});}catch(_){}showLogin();};

const pageMeta={
  overview:['Ana Panel',''],
  decision:['Kredi Kararı',''],
  history:['Başvurular',''],
  risk:['Kredi Riski',''],
  governance:['Politika & Yönetişim',''],
  science:['Gelişmiş Analizler','']
};
function goToPage(page){
  const pageEl=$(`#page-${page}`);if(!pageEl||pageEl.classList.contains('hidden'))return;
  currentPage=page;
  $$('.nav').forEach(x=>x.classList.toggle('active',x.dataset.page===page));$$('.page').forEach(x=>x.classList.toggle('active',x.id===`page-${page}`));
  $('#pageTitle').textContent=pageMeta[page][0];$('#pageSubtitle').textContent=pageMeta[page][1];window.scrollTo({top:0,behavior:'smooth'});
  if(page==='overview')loadOverview();if(page==='history')loadHistory();if(page==='governance')loadGovernance();
}
$$('.nav').forEach(b=>b.onclick=()=>goToPage(b.dataset.page));
$('#quickDecisionBtn').onclick=()=>goToPage('decision');$('#allHistoryBtn').onclick=()=>goToPage('history');const topNew=$('#topNewDecisionBtn');if(topNew)topNew.onclick=()=>goToPage('decision');

async function loadOverview(){
  try{
    const o=await api(`${API}/overview`);
    $('#ovPolicy').textContent=o.active_policy.name;$('#ovPolicyVersion').textContent=`Sürüm ${o.active_policy.version}`;$('#ovPolicySummary').textContent=o.active_policy.name;
    $('#ovModel').textContent=o.model_version;$('#ovDecisions').textContent=fmt(o.decision_count);$('#ovApproved').textContent=fmt(o.approved_count);$('#ovRejected').textContent=fmt(o.rejected_count);$('#ovSensitive').textContent=fmt(o.sensitive_count);
    renderRecent(o.recent_decisions||[]);
  }catch(e){if(/Oturum|şifre/i.test(e.message))showLogin();}
}
function renderRecent(rows){
  const target=$('#recentDecisions');clear(target);target.className='';
  if(!rows.length){target.className='empty-state';add(target,node('b','','Henüz karar yok.'),node('span','','Yeni kredi kararı oluşturduğunuzda burada görünecek.'));return;}
  const data=rows.map(r=>{const view=node('button','table-action','Aç');view.dataset.decisionId=r.id;view.title='Bu kredi kararının özetini açar';view.onclick=()=>openHistoryDecision(r.id);const dl=r.decision_label||r.decision;const stress=r.robustness_label||(r.stable===false?'HASSAS':'KARAR DEĞİŞMEDİ');return [formatDate(r.at),r.applicant_id,chip(decisionText(dl),decisionKind(dl)),r.recommended_limit?money(r.recommended_limit):'—',chip(stress,r.stable===false?'warn':'good'),view];});
  target.appendChild(table(['Tarih','Başvuru','Karar','Limit','Stres',''],data));
}

async function loadPolicies(){
  try{policies=await api(`${API}/governance/policies`);[$('#dPolicy')].filter(Boolean).forEach(select=>{clear(select);policies.forEach(p=>{const o=document.createElement('option');o.value=p.policy_id;o.textContent=`${p.name} · ${statusLabel(p.status)}`;o.selected=p.status==='active';select.appendChild(o);});});}catch(e){console.error(e);}
}
function decisionPayload(){
  const asDecimal=id=>Number($(id).value)/100;
  return {
    applicant_id:$('#dApplicant').value.trim(),
    product_type:$('#dProduct').value,
    term_months:Number($('#dTerm').value),
    repayment_type:$('#dRepayment').value,
    pd_basis:$('#dPdBasis').value,
    requested_amount:parseMoneyValue($('#dAmount').value),
    pd:asDecimal('#dPd'),lgd:asDecimal('#dLgd'),
    annual_rate:Number($('#dRate').value)*12/100,
    upfront_fee:parseMoneyValue($('#dFee').value),
    monthly_net_income:parseMoneyValue($('#dIncome').value),
    existing_monthly_debt_service:parseMoneyValue($('#dExistingDebt').value),
    collateral_value:parseMoneyValue($('#dCollateral').value),
    collateral_energy_class:$('#dEnergy').value,
    housing_bsmv_exempt:!!$('#dHousingBsmvExempt')?.checked,
    housing_has_other_home:!!$('#dHousingHasOtherHome')?.checked,
    applicant_age_years:Number($('#dApplicantAge')?.value||0),
    vehicle_is_used:!!$('#dVehicleIsUsed')?.checked,
    vehicle_age_years:Number($('#dVehicleAge')?.value||0),
    policy_id:$('#dPolicy').value,
    information_signal:{name:'Varsayımsal ek bilgi sinyali (simülasyon)',source_mode:'simulation',source_note:'Gerçek kredi bürosu verisi değildir; örnek olabilirlik matrisiyle yalnız bilgi değeri hesaplanır.',cost:parseMoneyValue($('#dInfoCost').value),signal_names:['yeşil','sarı','kırmızı'],signal_given_state:[[.78,.18,.04],[.30,.52,.18],[.08,.27,.65]]}
  };
}
function resetDecisionValidation(){
  ['#dApplicant','#dAmount','#dTerm','#dPd','#dLgd','#dPolicy','#dCollateral','#dApplicantAge','#dVehicleAge'].forEach(sel=>$(sel)?.classList.remove('input-invalid'));
}
function validateDecisionForm(){
  resetDecisionValidation();
  const issues=[];
  const applicant=$('#dApplicant').value.trim();
  const amount=parseMoneyValue($('#dAmount').value);
  const term=Number($('#dTerm').value),pd=Number($('#dPd').value),lgd=Number($('#dLgd').value);
  const flag=(selector,message)=>{const el=$(selector);el?.classList.add('input-invalid');issues.push(message);};
  if(!applicant)flag('#dApplicant','Başvuru numarasını girin.');
  if(!amount||amount<1)flag('#dAmount','Talep edilen kredi tutarı 0’dan büyük olmalıdır.');
  if(!Number.isInteger(term)||term<1||term>600)flag('#dTerm','Vade ay cinsinden 1 ile 600 arasında tam sayı olmalıdır.');
  if(!Number.isFinite(pd)||pd<=0||pd>=100)flag('#dPd','PD değerini yüzde olarak 0 ile 100 arasında girin. Örnek: %8 için 8.');
  if(!Number.isFinite(lgd)||lgd<0||lgd>100)flag('#dLgd','LGD değerini yüzde olarak 0 ile 100 arasında girin. Örnek: %55 için 55.');
  if(!$('#dPolicy').value)flag('#dPolicy','Bir karar politikası seçin.');
  if(['konut','tasit'].includes($('#dProduct').value)&&parseMoneyValue($('#dCollateral').value)<=0)flag('#dCollateral',$('#dProduct').value==='konut'?'Konut kredisi için ekspertiz/teminat değeri girin.':'Taşıt kredisi için fatura/kasko değerini girin.');
  if($('#dProduct').value==='tasit'&&$('#dVehicleIsUsed')?.checked&&Number($('#dVehicleAge')?.value||0)<=0)flag('#dVehicleAge','İkinci el taşıt için araç yaşını girin.');
  if($('#dProduct').value==='konut'&&Number($('#dApplicantAge')?.value||0)<18)flag('#dApplicantAge','Konut kredisi için başvuran yaşını girin.');
  if(issues.length){
    $('#decisionError').textContent=`Devam etmek için ${issues.length} alanı düzeltin: ${issues.join(' ')}`;
    const first=$('.input-invalid');first?.focus();return false;
  }
  return true;
}
const PUBLIC_RATE_REFERENCE={
  ihtiyac:{monthly:3.84,note:'Güncel referans verilere göre ihtiyaç kredisi aylık oranı: %3,84 (11.08.2026).'},
  konut:{monthly:3.15,note:'Güncel referans verilere göre konut kredisi aylık oranı: %3,15 (11.08.2026).'},
  ticari_taksitli:{monthly:52.48/12,note:'TCMB sektör referansı: yıllık %52,48 (31.07.2026); müşteri teklif oranı değildir.'},
  spot:{monthly:52.48/12,note:'TCMB sektör referansı: yıllık %52,48 (31.07.2026); müşteri teklif oranı değildir.'},
  diger:{monthly:56.91/12,note:'TCMB ihtiyaç kredisi sektör referansı: yıllık %56,91 (31.07.2026); müşteri teklifi değildir.'}
};
function publicRateFor(product,term){
  if(product==='tasit'){const m=term<=12?3.75:term<=24?3.70:term<=36?3.65:term<=48?3.60:null;return m?{monthly:m,note:`Güncel referans verilere göre taşıt kredisi aylık oranı: %${m.toFixed(2).replace('.',',')} (${term} ay seçimi; 11.08.2026).`}:null;}
  return PUBLIC_RATE_REFERENCE[product]||null;
}
function syncReferenceRate(){
  const ref=publicRateFor($('#dProduct')?.value,Number($('#dTerm')?.value||12));
  if(ref){$('#dRate').value=Number(ref.monthly).toFixed(2);if($('#dRateNote'))$('#dRateNote').textContent=`${ref.note} Müşteriye özel oran değişebilir.`;}
  else if($('#dRateNote'))$('#dRateNote').textContent='Bu ürün/vade için otomatik kamu oranı yok. Sözleşmedeki aylık nominal oranı girin.';
}
function syncProductFields(){
  const product=$('#dProduct')?.value;const isHousing=product==='konut',isVehicle=product==='tasit';
  $('#housingTaxField')?.classList.toggle('hidden',!isHousing);
  $('#housingOtherHomeField')?.classList.toggle('hidden',!isHousing);
  $('#housingAgeField')?.classList.toggle('hidden',!isHousing);
  $('#vehicleUsedField')?.classList.toggle('hidden',!isVehicle);
  $('#vehicleAgeField')?.classList.toggle('hidden',!isVehicle||!$('#dVehicleIsUsed')?.checked);
  const collateralDetails=$('#dCollateral')?.closest('details');if(collateralDetails&&(isHousing||isVehicle))collateralDetails.open=true;
  if($('#collateralLabel'))$('#collateralLabel').textContent=isHousing?'Konut ekspertiz değeri (TL)':isVehicle?'Taşıt fatura / kasko değeri (TL)':'Teminat / ekspertiz değeri (TL)';
  if($('#collateralHelp'))$('#collateralHelp').textContent=isVehicle?'Güncel taşıt kredi/değer ve vade kurallarının kontrolü için zorunludur. 2 milyon TL üzeri standart taşıt kredisi otomatik elenir.':isHousing?'BDDK LTV kontrolünde zorunludur; başka konut sahipliği seçilirse ilgili oran indirimi uygulanır.':'Teminat bilgisi varsa girin; LGD ayrı risk girdisidir.';
  if(!isHousing&&$('#dHousingBsmvExempt'))$('#dHousingBsmvExempt').checked=false;
  if(!isHousing&&$('#dHousingHasOtherHome'))$('#dHousingHasOtherHome').checked=false;
  if(!isHousing&&$('#dApplicantAge'))$('#dApplicantAge').value='0';
  if(isHousing&&$('#dApplicantAge')&&Number($('#dApplicantAge').value||0)<18)$('#dApplicantAge').value='35';
  if(!isVehicle&&$('#dVehicleIsUsed'))$('#dVehicleIsUsed').checked=false;
  if(!isVehicle&&$('#dVehicleAge'))$('#dVehicleAge').value='0';
  syncReferenceRate();
}
$('#dProduct')?.addEventListener('change',syncProductFields);
$('#dTerm')?.addEventListener('change',syncReferenceRate);
$('#dVehicleIsUsed')?.addEventListener('change',()=>{const isUsed=$('#dVehicleIsUsed').checked;$('#vehicleAgeField')?.classList.toggle('hidden',!isUsed);if(!isUsed&&$('#dVehicleAge'))$('#dVehicleAge').value='0';});
syncProductFields();

const productLabel=x=>({ihtiyac:'Bireysel ihtiyaç',konut:'Konut',tasit:'Taşıt',ticari_taksitli:'Taksitli ticari',spot:'Spot / vade sonu',diger:'Diğer'}[x]||x||'—');
const repaymentLabel=x=>({equal_installment:'Eşit taksit',equal_principal:'Eşit anapara',bullet:'Vade sonu anapara'}[x]||x||'—');
const pdBasisLabel=x=>({annual_12m:'12 aylık PD girdisi',lifetime:'Vade sonuna kadar PD girdisi'}[x]||x||'—');
$('#runDecision').onclick=async()=>{
  if(!validateDecisionForm())return;
  try{$('#decisionError').textContent='';const t=$('#decisionResult');clear(t);const loading=panel('Karar hesaplanıyor…','Risk, getiri ve stres senaryoları değerlendiriliyor.');loading.classList.add('empty-state');t.appendChild(loading);const r=await api(`${API}/decision/evaluate`,{method:'POST',json:decisionPayload()});renderDecision(r);loadOverview();loadHistory();}
  catch(e){$('#decisionError').textContent=e.message;const t=$('#decisionResult');clear(t);const p=panel('Karar üretilemedi','Girdi alanlarını kontrol edip yeniden deneyin.');p.classList.add('empty-state');t.appendChild(p);}
};
function renderDecision(r){
  const target=$('#decisionResult');clear(target);
  const econ=r.economics||{},info=r.information_value,science=r.decision_science||{},a=r.applicant||{},loan=r.loan_economics||{},market=r.market_context||{};
  const appRisk=r.application_risk||{},requested=r.requested_scenario||{},reqEcon=requested.economics||{},reqLoan=requested.loan_economics||{},reqPricing=requested.pricing||{};
  const controls=r.policy_controls||[],warnings=r.data_quality_warnings||[],approved=r.decision==='ONAY'&&Number(r.recommended_limit||0)>0;
  const partial=r.decision_label==='KISMİ ONAY',stable=!!r.robustness?.stable_across_scenarios;
  const label=r.decision_label||(approved?'ONAY':'REDDET');
  const displayLoan=approved?loan:reqLoan,displayEcon=approved?econ:reqEcon,displayPricing=approved?(r.pricing||{}):reqPricing;
  const moneyDash=v=>v==null?'—':money(v),pctDash=v=>v==null?'—':pct(v);

  const hero=panel('Karar sonucu','');hero.classList.add('decision-hero-card',approved?'approved':'rejected');
  const row=node('div','decision-hero'),left=node('div');
  const title=approved?`${label} · ${money(r.recommended_limit)}`:'REDDET';
  add(left,node('span','decision-label','K-RISK KREDİ KARARI'),node('div','decision-title',title),node('div','decision-sub',`${productLabel(a.product_type)} · ${a.term_months||'—'} ay · ${repaymentLabel(a.repayment_type)} · ${r.policy?.name||'Politika'}`));
  add(row,left,node('span',`decision-badge ${approved?'good':'bad'}`,label));hero.appendChild(row);
  const mr=node('div','metric-row v4-metrics');
  add(mr,
    metric('Talep edilen',money(a.requested_amount||0),'başvuru tutarı'),
    metric('Önerilen limit',approved?money(r.recommended_limit):'—',approved?(partial?'kısmi uygun limit':'uygun limit'):'pozitif uygun limit yok'),
    metric('12 aylık PD',pctDash(appRisk.pd_12m??a.pd),pdBasisLabel(a.pd_basis)),
    metric('İlk taksit',approved?moneyDash(loan.monthly_payment):'—',approved?'vergi/fon dahil':'kredi kullandırımı yok')
  );hero.appendChild(mr);target.appendChild(hero);

  const rationale=panel('Karar gerekçesi','');rationale.classList.add('decision-rationale');
  const rb=node('div','decision-rationale-main');
  add(rb,node('span','decision-rationale-kicker',approved&&partial?'TAM TALEBİ SINIRLAYAN ANA KONTROL':approved?'SONUÇ':'ANA RED NEDENİ'),node('b','',r.primary_reason||(approved?'Politika kontrolleri geçti':'Uygun pozitif limit bulunamadı')),node('p','',r.decision_summary||''));
  rationale.appendChild(rb);
  if((r.secondary_reasons||[]).length){const sec=node('div','decision-secondary-reasons');sec.appendChild(node('span','','DİĞER BAĞLAYICI KONTROLLER'));(r.secondary_reasons||[]).forEach(x=>sec.appendChild(node('b','',x)));rationale.appendChild(sec);}
  if(Number(r.max_feasible_limit||0)>0&&Number(r.max_feasible_limit)<Number(a.requested_amount||0)){const cap=node('div','decision-limit-cap');add(cap,node('span','','POLİTİKA İÇİ MAKSİMUM'),node('strong','',money(r.max_feasible_limit)),node('small','', 'en yüksek uygun limit'));rationale.appendChild(cap);}
  target.appendChild(rationale);

  if(warnings.length){const dq=panel('Girdi kontrolü','Kararı değiştirmeyen fakat doğrulanması gereken olağandışı girdiler.');warnings.forEach(w=>{const x=node('div',`data-warning ${w.severity||'medium'}`);add(x,node('b','',w.severity==='high'?'Girdiyi doğrulayın':'Kontrol önerisi'),node('span','',w.message));dq.appendChild(x);});target.appendChild(dq);}

  const core=panel('Risk ve ekonomi özeti','Başvuru riski ile seçilen kararın ekonomisi birbirinden ayrıdır.');core.classList.add('core-summary');
  const corem=node('div','metric-row');add(corem,
    metric('Müşteri faizi',pct((a.annual_rate||0)/12),'aylık · '+pct(a.annual_rate||0)+' yıllık nominal'),
    metric(approved?'Seçilen limit fiyat tabanı':'Talep fiyat tabanı',pctDash(displayPricing.risk_adjusted_floor_rate),`durum ${displayPricing.floor_status||'—'}`),
    metric('Başvuru 12 aylık PD',pctDash(appRisk.pd_12m??a.pd),'REDDET/ONAY aksiyonundan bağımsız'),
    metric(approved?'Seçilen limit EL':'Talep verilseydi EL',moneyDash(displayEcon.expected_loss),approved?'vade boyunca beklenen zarar':'talep edilen tutarın risk görünümü')
  );core.appendChild(corem);target.appendChild(core);

  const deep=node('details','analysis-details');deep.appendChild(node('summary','','Ayrıntılı analizi göster'));const deepBody=node('div','analysis-details-body');deep.appendChild(deepBody);target.appendChild(deep);

  const bank=panel('Kararı etkileyen politika kontrolleri','Talep edilen tutar üzerinde çalışan kontroller.');
  const controlValue=(v,unit,isLimit=false)=>{if(v==null)return isLimit?'Zorunlu':'—';if(unit==='oran')return pctDash(v);if(unit==='TL')return moneyDash(v);return `${fmt(v,0)} ${unit||''}`.trim();};
  const checkRows=controls.map(x=>[x.name,chip(x.status,x.status==='PASS'?'good':x.status==='UYARI'?'warn':'bad'),controlValue(x.actual,x.unit),controlValue(x.limit,x.unit,true),x.source||'—']);
  if(checkRows.length)bank.appendChild(table(['Kontrol','Durum','Gerçekleşen','Sınır','Kaynak'],checkRows));
  else{const empty=node('div','empty-state');add(empty,node('b','','Politika kontrol kaydı bulunamadı.'),node('span','','Bu karar için kontrol özeti üretilemedi.'));bank.appendChild(empty);}deepBody.appendChild(bank);

  const contract=panel(approved?'Kredi ekonomisi · seçilen limit':'Kredi ekonomisi · talep senaryosu',approved?'Önerilen limit için nakit akışı ve risk metrikleri.':'REDDET aksiyonunun 0 TL değerleri yerine, talep edilen kredinin varsayımsal ekonomik görünümü gösterilir.');
  const cm=node('div','metric-row');
  add(cm,
    metric('En yüksek dönem ödemesi',moneyDash(displayLoan.max_contractual_payment??displayLoan.monthly_payment),`ay ${displayLoan.max_contractual_payment_period||1}`),
    metric('Beklenen NPV',moneyDash(displayEcon.expected_npv),approved?'seçilen limit':'talep verilseydi'),
    metric('Beklenen zarar',moneyDash(displayEcon.expected_loss),approved?'seçilen limit':'talep verilseydi'),
    metric('Pilot RAROC',pctDash(displayEcon.raroc),approved?'seçilen limit':'talep verilseydi')
  );contract.appendChild(cm);
  const cm2=node('div','metric-row');add(cm2,
    metric('Toplam müşteri ödemesi',moneyDash(displayLoan.contractual_total_payment),'temerrüt yok varsayımı'),
    metric('Vade PD',pctDash(appRisk.term_pd??displayLoan.term_pd),`${a.term_months||0} aylık ufuk`),
    metric('12 aylık EL',moneyDash(displayEcon.expected_loss_12m),'politika ufku'),
    metric('Başabaş yıllık oran',pctDash(displayPricing.break_even_rate),'NPV = 0 referansı')
  );contract.appendChild(cm2);
  if(!approved){const note=node('div','risk-inline-note');add(note,node('b','','Neden “0 TL” göstermiyoruz?'),node('span','','REDDET aksiyonunda kredi kullandırımı olmadığı için seçilen aksiyonun taksiti, NPV’si ve EL’si doğal olarak 0’dır. Bunlar müşterinin başvuru riskini anlatmadığından ana metrik olarak kullanılmaz.'));contract.appendChild(note);}deepBody.appendChild(contract);

  const maturity=panel(approved?'Ödeme planı':'Talep verilseydi ödeme planı',approved?'Seçilen limitin aylık ödeme planı.':'Karar verilmesine neden olan ödeme yükünü görmek için talep edilen tutarın varsayımsal planı.');
  const sched=displayLoan.schedule||[];const shown=sched.length<=13?sched:[...sched.slice(0,12),sched[sched.length-1]];
  if(shown.length)maturity.appendChild(table(['Ay','Açılış','Taksit','Faiz','BSMV','KKDF','Anapara','Kapanış'],shown.map(x=>[x.period,money(x.opening_balance),money(x.payment),money(x.interest),money(x.bsmv||0),money(x.kkdf||0),money(x.principal),money(x.closing_balance)])));
  else maturity.appendChild(small('Ödeme planı oluşmadı.'));deepBody.appendChild(maturity);

  const next=panel('Sonuç özeti','');const nb=node('div','next-action');
  add(nb,node('b','',label),node('span','',r.decision_summary||'Karar özeti bulunmuyor.'));next.appendChild(nb);target.appendChild(next);

  const risk=panel('Stres testi','Kararın farklı makro senaryolarda nasıl değiştiği.');
  const status=node('div','stress-status');add(status,node('span','','KARAR DAYANIKLILIĞI'),node('strong','',r.robustness?.label||(stable?'KARAR DEĞİŞMEDİ':'HASSAS')));risk.appendChild(status);
  const sr=node('div','scenario-row');(r.robustness?.scenarios||[]).forEach(s=>{const box=node('div','scenario');const shock=s.scenario==='baz'?'Mevcut varsayımlar':`PD ×${Number(s.pd_multiplier||1).toFixed(2)} · LGD ×${Number(s.lgd_multiplier||1).toFixed(2)} · fonlama +${((s.funding_add||0)*100).toFixed(1)} puan`;add(box,node('span','',stateName(s.scenario)),node('strong','',s.recommended_limit?money(s.recommended_limit):'REDDET'),small(shock));sr.appendChild(box);});risk.appendChild(sr);deepBody.appendChild(risk);

  const marketPanel=panel('Piyasa ve fonlama referansları','Karar hesabında kullanılan vekil ile kamu referansı ayrıdır.');
  const flow=market.public_lending_reference||{},bankRate=market.akbank_customer_rate_reference||{};const productMarketRate=a.product_type==='konut'?flow.housing_loan_rate:a.product_type==='tasit'?flow.vehicle_loan_rate:['ticari_taksitli','spot'].includes(a.product_type)?flow.tl_commercial_loan_rate:flow.consumer_loan_rate;const mm=node('div','metric-row compact-market');add(mm,metric('Müşteri aylık faizi',pct((a.annual_rate||0)/12),'SÖZLEŞME / GİRDİ'),metric('Güncel referans oran',bankRate.monthly_rate!=null?pct(bankRate.monthly_rate):'—',bankRate.as_of?`REFERANS · ${bankRate.as_of}`:'ürün bazında yok'),metric('TCMB sektör akım faizi',productMarketRate!=null?pct(productMarketRate):'—',`YILLIK · ${flow.as_of||'—'}`),metric('TCMB politika faizi',pct(market.tcmb_policy_rate||0),`REFERANS · ${market.as_of||'—'}`));marketPanel.appendChild(mm);marketPanel.appendChild(small(`${market.note||''} Pilot fonlama vekili: gerçek FTP değil.`));deepBody.appendChild(marketPanel);

  if(canDownloadReport()){
    const report=panel('Karar izlenebilirlik raporu','Ana neden, politika kontrolleri, dinamik limit, ekonomi ve stres sonuçları tek PDF’de.');report.classList.add('report-card');
    const actions=node('div','report-actions');add(actions,reportButton(r.decision_id,'PDF Raporunu İndir'),node('span','',`Karar No: ${String(r.decision_id).slice(0,12)} · Platform V14`));report.appendChild(actions);target.appendChild(report);
  }

  if(info){const p=panel('Ek Bilgi Değeri Analizi','Ek bilgi karar değerini değiştiriyor mu?');const notice=node('div','simulation-banner');add(notice,chip(info.is_simulation?'SİMÜLASYON':'TANIMLI KAYNAK',info.is_simulation?'warn':'neutral'),node('span','',info.interpretation||info.source_note||''));p.appendChild(notice);const evpiRatio=Number(a.requested_amount||0)>0?Number(science.evpi||0)/Number(a.requested_amount):0;const im=node('div','metric-row');add(im,metric('Risk-ayarlı EVSI',money(info.evsi),'tanımlı sinyalin karar değeri'),metric('Bilgi maliyeti',money(info.cost),'tanımlı maliyet'),metric('Ek bilginin net değeri',money(info.net_value),'EVSI − maliyet',info.net_value>=0?'positive':'negative'),metric('Risk-ayarlı EVPI',money(science.evpi),`teorik üst sınır · talebin ${pct(evpiRatio)}`));p.appendChild(im);const d=node('details','advanced-results');d.appendChild(node('summary','','Sinyal sonrası olasılıkları göster'));d.appendChild(table(['Sinyal','Olasılık','Sonsal PD','Kesinlik eşdeğeri'],(info.signals||[]).map(x=>[x.signal,pct(x.probability),pct(x.posterior_pd),money(x.certainty_equivalent)])));p.appendChild(d);deepBody.appendChild(p);}

  const advanced=panel('Teknik ayrıntılar','Risk/model ekibi için denetim görünümü.');const det=node('details','advanced-results');det.appendChild(node('summary','','Teknik hesapları göster'));
  const dmr=node('div','metric-row');add(dmr,metric('Başvuru PD',pctDash(appRisk.pd_12m??a.pd),'12 aylık'),metric('Maksimum uygun limit',r.max_feasible_limit?money(r.max_feasible_limit):'—','dinamik çözücü'),metric('Risk-ayarlı EVPI',money(science.evpi),'aynı fayda kriteri'),metric('Talep fiyat tabanı',pctDash(reqPricing.risk_adjusted_floor_rate),`durum ${reqPricing.floor_status||'—'}`));det.appendChild(dmr);
  det.appendChild(table(['Aksiyon','Limit','Beklenen sonuç','Lifetime EL','12m EL','Pilot RAROC','Risk sınırı'],(r.decision_candidates||r.actions||[]).map(x=>[x.action,money(x.limit),money(x.expected_profit),money(x.expected_loss),money(x.expected_loss_12m),pct(x.raroc),x.feasible?'UYGUN':(x.failed_constraints||[]).join(', ')])));advanced.appendChild(det);deepBody.appendChild(advanced);
}

async function loadHistory(){
  try{historyRows=await api(`${API}/decision/history?limit=100`);renderHistory();}catch(e){const t=$('#historyTable');if(t)t.textContent=e.message;}
}
function renderHistory(){
  const target=$('#historyTable');if(!target)return;clear(target);target.className='';const q=($('#historySearch').value||'').trim().toLocaleLowerCase('tr-TR');const rows=historyRows.filter(x=>{const r=x.result||{};return !q||[x.applicant_id,x.actor,r.decision,r.policy?.name].join(' ').toLocaleLowerCase('tr-TR').includes(q);});$('#historyCount').textContent=`${rows.length} kayıt`;
  if(!rows.length){target.className='empty-state';add(target,node('b','','Eşleşen kayıt bulunamadı.'),node('span','','Aramayı değiştirin veya yeni bir kredi kararı oluşturun.'));return;}
  const data=rows.map(x=>{const r=x.result||{},ov=x.override;const decision=ov?.decision||(r.decision_label||r.decision),limit=ov?.limit??r.recommended_limit;const actions=node('div','row-actions');const b=node('button','table-action','Aç');b.title='Karar ayrıntısını ve varsa yönetici raporunu açar';b.onclick=()=>openHistoryDecision(x.id);actions.appendChild(b);if(canDownloadReport())actions.appendChild(reportButton(x.id,'PDF'));return [formatDate(x.at),x.applicant_id,chip(decisionText(decision),decisionKind(decision)),limit?money(limit):'—',r.policy?.name||x.policy_id,actions];});target.appendChild(table(['Tarih','Başvuru','Karar','Limit','Politika','İşlem'],data));
}
$('#refreshHistory').onclick=loadHistory;$('#historySearch').addEventListener('input',renderHistory);
async function openHistoryDecision(id){
  try{
    const rec=await api(`${API}/decision/${encodeURIComponent(id)}`);goToPage('history');const target=$('#historyDetail');clear(target);const r=rec.result||{};
    const p=panel(`Karar detayı · ${rec.applicant_id}`,`Karar No ${String(rec.id).slice(0,12)} · ${formatDate(rec.at)}`);
    const mr=node('div','metric-row');add(mr,metric('Karar',rec.override?.decision||r.decision,'son geçerli karar'),metric('Limit',money(rec.override?.limit??r.recommended_limit),'önerilen / geçerli'),metric('Politika',r.policy?.name||rec.policy_id,r.policy?.version||''),metric('Oluşturan',rec.actor,''));p.appendChild(mr);
    if(rec.override){const o=node('div','next-action');add(o,node('b','','Yetkili insan kararı mevcut'),node('span','',`${rec.override.actor}: ${rec.override.reason}`));p.appendChild(o);}
    if(canDownloadReport()){const a=node('div','history-report');add(a,node('div','', ''),reportButton(rec.id,'Karar Nasıl Alındı? PDF'));const copy=node('div');add(copy,node('b','','Yönetici karar raporu'),node('span','','Girdiler, politika, alternatifler, ekonomik sonuç ve stres adımlarını tek PDF’de gösterir.'));a.replaceChild(copy,a.firstChild);p.appendChild(a);}
    target.appendChild(p);
  }catch(e){$('#historyDetail').textContent=e.message;}
}


async function loadGovernance(){
  try{
    const base=[api(`${API}/governance/policies`),api(`${API}/governance/model`),api(`${API}/governance/audit?limit=25`)];
    if(user?.role==='admin')base.push(api(`${API}/governance/users`));
    const [ps,m,a,users]=await Promise.all(base);
    const pt=$('#policyTable');clear(pt);pt.appendChild(table(['Politika','Durum','Risk toleransı','Kalibrasyon','Sermaye modeli','Açıklama'],ps.map(p=>[`${p.name} ${p.version}`,chip(statusLabel(p.status),p.status==='active'?'good':'warn'),money(p.risk_tolerance_tl),p.risk_calibration_status==='approved'?'Onaylı':'Pilot',p.capital_model_status==='approved'?'Onaylı':'Pilot',p.description])));
    const mg=$('#modelGovernance');clear(mg);[['Uygulama sürümü',m.app_version],['Karar modeli',m.model_version],['Durum',statusLabel(m.status)],['Mimari',m.architecture],['Canlı kullanım','Kuruma özel validasyon ve güvenlik onayı gerekir']].forEach(([k,v])=>{const row=node('div','kv');add(row,node('span','',k),node('b','',v));mg.appendChild(row);});
    const at=$('#auditTable');clear(at);at.appendChild(table(['Zaman','Kullanıcı','Olay','Varlık'],a.map(x=>[formatDate(x.at),x.actor,x.action,`${x.entity_type} · ${String(x.entity_id).slice(0,12)}`])));
    if(user?.role==='admin'&&users){const ut=$('#usersTable');clear(ut);ut.appendChild(table(['Kullanıcı','Rol','Durum','İlk şifre değişimi','Oluşturulma'],users.map(x=>[x.username,roleLabel(x.role),x.locked?'Geçici kilitli':(x.is_active?'Aktif':'Pasif'),x.must_change_password?'Bekleniyor':'Tamamlandı',formatDate(x.created_at)])));}
  }catch(e){$('#auditTable').textContent=e.message;}
}
$('#refreshAudit').onclick=loadGovernance;
$('#createUserBtn').onclick=async()=>{
  const msg=$('#createUserMessage'),password=$('#newUserPass').value,password2=$('#newUserPass2').value;msg.textContent='';msg.className='alert';
  if(password!==password2){msg.textContent='Şifreler birbiriyle aynı değil.';msg.classList.add('error');return;}
  try{const r=await api(`${API}/governance/users`,{method:'POST',json:{username:$('#newUsername').value.trim(),password,role:$('#newUserRole').value}});msg.textContent=`${r.username} hesabı oluşturuldu. Kullanıcı ilk girişte şifresini değiştirecek.`;msg.classList.add('success');$('#newUsername').value='';$('#newUserPass').value='';$('#newUserPass2').value='';loadGovernance();}
  catch(e){msg.textContent=e.message;msg.classList.add('error');}
};


// Credit Risk & Stress Intelligence
function riskDecimal(id){return Number($(id)?.value||0)/100;}
function renderSingleRisk(ead,r){
  const target=$('#singleRiskResult');clear(target);target.className='result-stack';
  const p=panel('Tek kredi risk özeti','Sabit EAD/LGD ve iki-durumlu temerrüt varsayımı altında temel risk ölçüleri.');
  const mr=node('div','metric-row');
  add(mr,metric('EAD',money(ead.ead),'temerrüt anındaki risk tutarı'),metric('Beklenen Kayıp · EL',money(r.expected_loss),pct(r.expected_loss_rate)),metric('Beklenmeyen Kayıp · UL',money(r.unexpected_loss),pct(r.unexpected_loss_rate)),metric(`Credit VaR · ${fmt(r.confidence*100,1)}%`,money(r.credit_var),'iki-durumlu kayıp eşiği'));
  p.appendChild(mr);
  const detail=node('div','risk-inline-note');add(detail,node('b','','Formül özeti'),node('span','',`EAD = ${money(ead.drawn_amount)} + ${pct(ead.ccf)} × ${money(ead.undrawn_amount)} = ${money(ead.ead)} · Recovery Rate ${pct(r.recovery_rate)} · Ekonomik sermaye ${money(r.economic_capital)}` ));p.appendChild(detail);target.appendChild(p);
}
$('#runSingleRisk').onclick=async()=>{
  try{
    $('#singleRiskError').textContent='';
    const ead=await api(`${API}/risk/ead`,{method:'POST',json:{drawn_amount:parseMoneyValue($('#riskDrawn').value),undrawn_amount:parseMoneyValue($('#riskUndrawn').value),ccf:riskDecimal('#riskCcf')}});
    const r=await api(`${API}/risk/single`,{method:'POST',json:{exposure:{exposure_id:'ETKILESIMLI-RISK',pd:riskDecimal('#riskPd'),lgd:riskDecimal('#riskLgd'),ead:ead.ead,sector:'etkilesimli'},confidence:riskDecimal('#riskConfidence')}});
    renderSingleRisk(ead,r);
  }catch(e){$('#singleRiskError').textContent=e.message;}
};

const science=[['Karar problemi','Eylem × doğa durumu × kazanç matrisi'],['MaxiMin','En kötü durumun en iyi aksiyonu'],['MaxiMax','En yüksek potansiyel kazanç'],['MiniMax pişmanlık','Maksimum fırsat kaybını küçültür'],['Kazanç / kayıp','Kazanç ve fırsat kaybı matrisleri'],['Beklenen değer','Olasılık ağırlıklı ekonomik sonuç'],['EVPI','Mükemmel bilginin üst fiyatı'],['Bayes','Önsel × olabilirlik → sonsal'],['Beta–Binom','Başarı / temerrüt oranı güncelleme'],['Gamma–Poisson','Olay sayısı / yoğunluk güncelleme'],['Ardışık Bayes','Sonsal yeni önsel olur'],['Örnekleme','Yerine koymalı / koymasız olabilirlik'],['EVSI','Örnek bilginin beklenen değeri'],['Doğrusal kazanç','Kritik μ ve kesişim'],['Normal karar','z, kritik oran, optimal miktar'],['Fayda ve risk','Beklenen fayda, kesinlik eşdeğeri, risk primi']];
function renderScienceMap(){const t=$('#scienceMap');clear(t);science.forEach((x,i)=>{const w=node('div'),s=node('section');add(s,node('strong','',x[0]),node('span','',x[1]));add(w,node('b','',i+1),s);t.appendChild(w);});}
$('#runBayes').onclick=async()=>{try{const r=await api(`${API}/science/bayes/binomial`,{method:'POST',json:{alpha:+$('#bAlpha').value,beta:+$('#bBeta').value,successes:+$('#bSuccess').value,failures:+$('#bFailure').value}});const t=$('#bayesResult');clear(t);add(t,document.createTextNode('Önsel ortalama '),node('b','',pct(r.prior.mean)),document.createTextNode(' → sonsal ortalama '),node('b','',pct(r.posterior.mean)),document.createElement('br'),document.createTextNode(`Bir sonraki önsel: Beta(${fmt(r.next_prior.alpha)}, ${fmt(r.next_prior.beta)})`));}catch(e){$('#bayesResult').textContent=e.message;}};
$('#runNormal').onclick=async()=>{try{const r=await api(`${API}/science/normal/newsvendor`,{method:'POST',json:{mean:+$('#nMean').value,std:+$('#nStd').value,price:+$('#nPrice').value,cost:+$('#nCost').value,salvage:20}});const t=$('#normalResult');clear(t);add(t,document.createTextNode('Kritik oran '),node('b','',pct(r.critical_ratio)),document.createTextNode(' · z '),node('b','',fmt(r.z,3)),document.createTextNode(' · optimal miktar '),node('b','',fmt(r.optimal_quantity,1)));}catch(e){$('#normalResult').textContent=e.message;}};

const helpData={
  ead:['EAD · Temerrüt Halinde Risk','Temerrüt gerçekleştiği anda bankanın riskte olan tutarıdır. K-Risk; kullanılmış tutar + CCF × kullanılmamış limit biçiminde hesaplayabilir.','Kredi Riski'],
  ccf:['CCF · Kredi Dönüşüm Faktörü','Kullanılmamış limitin temerrüt anına kadar ne kadarının kullanılabileceğini EAD hesabına taşıyan orandır. Kurumun ürün ve model politikasına göre belirlenmelidir.','Kredi Riski'],
  unexpected_loss:['UL · Beklenmeyen Kayıp','Kayıp dağılımının standart sapması/oynaklığıdır. Beklenen kaybın ötesindeki belirsizliği ve sermaye ihtiyacını anlamaya yardım eder.','Kredi Riski'],
  credit_var:['Credit VaR','Belirli güven düzeyinde aşılması beklenmeyen kredi kaybı eşiğidir. Bu ekranda tek kredi için analitik bir risk ölçüsü olarak gösterilir.','Kredi Riski'],
  economic_capital:['Ekonomik Sermaye','Risk laboratuvarında Credit VaR − EL olarak gösterilen kuyruk kaybı tamponudur. Düzenleyici sermaye hesabı değildir.','Kredi Riski'],
  applicant:['Başvuru numarası','Bankanın kredi başvurusuna verdiği benzersiz referanstır. Gerçek entegrasyonda başvuru sisteminden otomatik gelebilir.','Kredi Kararı'],
  amount:['Talep edilen kredi tutarı','Müşterinin istediği brüt kredi tutarıdır. Rakamları düz yazabilirsiniz; 1500000 otomatik olarak 1.500.000 biçimine dönüşür; kuruş gerekiyorsa virgül kullanılır (ör. 1.500.000,50).','Kredi Kararı'],
  product_type:['Kredi ürünü','Kredi ürününün ekonomik ve operasyonel davranışını belirler. İhtiyaç, konut, taşıt, taksitli ticari ve spot krediler aynı vade/teminat mantığıyla değerlendirilmez.','Kredi Sözleşmesi'],
  loan_purpose:['Kredi amacı','Kredinin hangi ihtiyaç, yatırım, işletme sermayesi veya proje için kullanılacağını belirtir. Günlük kredi incelemesinde amacın açık olması temel bir kontrol alanıdır.','Kredi Sözleşmesi'],
  repayment_source:['Geri ödeme kaynağı','Kredinin hangi gelir veya nakit akışıyla geri ödeneceğini belirtir. Bireyselde düzenli gelir, ticari kredide faaliyet veya proje nakit akışı gibi kaynaklar kullanılır.','Kredi Sözleşmesi'],
  term:['Vade (ay)','Kredinin anapara ve faizinin geri ödeneceği toplam süredir. K-Risk vadesiz kredi kararı üretmez; nakit akışı ve risk ufku bu alan üzerinden kurulur.','Kredi Sözleşmesi'],
  repayment_type:['Geri ödeme yapısı','Eşit taksit, eşit anapara veya vade sonu anapara seçenekleri aylık bakiye ve faiz profilini değiştirir.','Kredi Sözleşmesi'],
  pd_basis:['PD ufku','Girilen PD’nin 12 aylık mı yoksa kredi vadesine ait lifetime PD mi olduğunu belirtir. K-Risk iki ufku aynı kabul etmez.','Risk'],
  income:['Aylık net gelir / nakit akışı','Bireysel müşteri için aylık net gelir; ticari müşteride kurumun onayladığı nakit akışı göstergesi olarak kullanılır. Ödeme gücü oranı bu değer üzerinden hesaplanır.','Ödeme Gücü'],
  debt_service:['Mevcut aylık borç servisi','Müşterinin mevcut kredilerinden kaynaklanan aylık ödeme yüküdür. Yeni kredi taksitiyle birlikte toplam borç servisine eklenir.','Ödeme Gücü'],
  fee:['Peşin ücret / komisyon','Kredinin başlangıcında tahsil edildiği varsayılan ve ekonomik katkıya eklenen ücret/komisyon geliridir. Gerçek bankada ürün ve mevzuat kurallarıyla beslenmelidir.','Ekonomi'],
  collateral:['Teminat / ekspertiz değeri','Konut LTV kontrolünde kullanılır. K-Risk teminat değerinden otomatik LGD üretmez; LGD ayrı/onaylı bir risk modelinden veya girdiden gelmelidir.','Teminat'],
  energy_class:['Konut enerji sınıfı','Konut finansmanında tanımlı kredi/değer oranı referanslarının enerji sınıfına göre farklılaşabildiği durumlarda kullanılır.','Teminat'],
  housing_tax:['Konut BSMV istisnası','Konut finansmanında KKDF %0 profili kullanılır. BSMV istisnası koşullu olduğundan yalnız şartlar ayrıca teyit edilmişse bu kutu işaretlenir.','Vergi / Fon'],
  policy:['Karar politikası','Bankanın risk iştahını ve karar sınırlarını temsil eder. Aktif politika günlük kredi kararında kullanılan varsayılan stratejidir.','Politika'],
  pd:['Temerrüt Olasılığı (PD)','Müşterinin belirli bir dönem içinde temerrüde düşme olasılığıdır. Ekranda yüzde girilir: 8 yazmanız %8 anlamına gelir. PD yükseldikçe risk artar.','Risk'],
  lgd:['Temerrütte Zarar (LGD)','Temerrüt gerçekleştiğinde risk tutarının ne kadarının kaybedileceğine ilişkin oran varsayımıdır. 55 yazmak %55 anlamına gelir.','Risk'],
  ead:['Temerrüt Anındaki Risk (EAD)','Temerrüt anında bankanın risk altında kalan parasal tutarıdır. Kredi kararında limit ve kullanım yapısıyla ilişkilidir.','Risk'],
  segment:['Müşteri segmenti','Başvurunun Bireysel, KOBİ veya Ticari müşteri grubunda olduğunu belirtir. Banka entegrasyonunda bu bilgi müşteri sisteminden gelebilir.','Başvuru'],
  rate:['Aylık kredi faiz oranı','Güncel bireysel kredi uygulamalarında oran aylık olarak değerlendirilir. Ekrana örneğin 3,84 yazmak aylık %3,84 demektir; motor bunu yıllık nominal orana çevirip nakit akışında aylık orana geri dönüştürür. Referans oran müşteriye özel teklif değildir.','Ekonomi'],
  funding:['Pilot fonlama vekili','Gerçek banka FTP verisi bağlı olmadığı için güncel TL mevduat akım faizi şeffaf bir pilot vekil olarak kullanılır. Politika faizi veya gerçek FTP ile aynı kavram değildir.','Ekonomi'],
  operation_cost:['Operasyon maliyeti','Tahsis, inceleme, servis ve operasyon süreçlerinin başvuruya atanan parasal maliyetidir.','Ekonomi'],
  capital:['Sermaye maliyeti','Kredinin tükettiği risk sermayesinin ekonomik maliyetini temsil eden varsayımdır. Risk-ayarlı getiri hesabına etki eder.','Ekonomi'],
  late_probability:['Geç ödeme olasılığı','Temerrüt oluşmadan gecikmeli ödeme yaşanması ihtimalidir. Ara durumun ekonomik etkisini modellemek için kullanılır.','Risk'],
  late_loss:['Geç ödeme kayıp oranı','Gecikmeli ödeme olduğunda tahsilat, zaman ve operasyon etkisinin ekonomik kayıp oranıdır.','Risk'],
  evsi:['Risk-Ayarlı Ek Bilgi Değeri (EVSI)','K-Risk, her sinyal sonrası Bayes posteriorunu oluşturur; PD/EL/RAROC politika sınırlarını yeniden uygular ve aynı üstel fayda/risk toleransı kriteriyle bilginin parasal kesinlik-eşdeğeri değerini hesaplar. Bu değer yalnız ekonomik bilgi farkını gösterir; K-Risk satın al/alma önerisi üretmez.','Karar Bilimi'],
  evpi:['Risk-Ayarlı Mükemmel Bilgi Değeri (EVPI)','K-Risk, EVPI ve EVSI için aynı üstel fayda, risk toleransı ve politika guardrail kriterini kullanır. Bu nedenle örnek bilgi değeri teorik olarak mükemmel bilgi değerini aşamaz.','Karar Bilimi'],
  raroc:['Pilot RAROC','Getiriyi K-Risk’in pilot ekonomik sermaye yaklaşımıyla birlikte gösterir. Gerçek bankanın ICAAP/düzenleyici sermaye RAROC’u değildir.','Ekonomi'],
  expected_profit:['Beklenen ekonomik sonuç','Perform, gecikme ve temerrüt gibi olası durumların bugünkü değer cinsinden ekonomik sonuçlarının olasılıklarla ağırlıklandırılmış ortalamasıdır.','Ekonomi'],
  npv:['Beklenen ekonomik NPV','Gelecekteki ekonomik marj, kayıp ve sermaye maliyetlerinin bugünkü değere indirgenmiş beklenen toplamıdır. Standalone pilotta kurum FTP/fonlama girdisini düz iskonto oranı olarak kullanır.','Ekonomi'],
  expected_loss:['Beklenen zarar','Kredi riskinin beklenen parasal kaybını ifade eder. PD, LGD ve risk tutarı temel belirleyicilerdir.','Risk'],
  stress:['Stres testi','Aynı başvurunun baz, yavaşlama ve ağır stres koşullarında tekrar değerlendirilmesidir. Karar değişiyorsa sistem “ikinci kontrol” uyarısı verir.','Risk'],
  audit:['Denetim izi','Kimin, ne zaman, hangi karar/rapor/kullanıcı işlemini yaptığını değişmez olay kaydı mantığıyla izlemek için kullanılır.','Yönetişim'],
  role:['Kullanıcı rolü','Kredi Analisti günlük kararları; Risk Yöneticisi gelişmiş risk ve yönetişim alanlarını; Yönetici ayrıca kullanıcı yönetimini kullanabilir.','Güvenlik'],
  bayes:['Bayes güncellemesi','Yeni kanıt geldikçe önsel olasılık güncellenir. Önceki sonsal, bir sonraki güncellemenin önseli olur.','Karar Bilimi'],
  beta_prior:['Beta önseli · Alfa / Beta','Beta dağılımındaki alfa ve beta parametreleri başarı oranı hakkındaki başlangıç inancının şeklini ve gücünü belirler.','Karar Bilimi'],
  bayes_observation:['Bayes gözlemleri','Yeni dönemde görülen başarı ve başarısızlık sayıları önsel bilgiyle birleştirilerek sonsal dağılımı oluşturur.','Karar Bilimi'],
  normal:['Normal dağılım altında karar','Belirsiz talep veya miktar problemlerinde kritik oran ve z değeri üzerinden ekonomik olarak optimal miktarı hesaplar.','Karar Bilimi']
};
const generalHelp=[
 ['ONAY / REDDET','K-Risk karar önerisi üretir. Gerçek banka ortamında nihai yetki bankanın yetki matrisi ve kredi iş akışında kalır.','Karar'],
 ['Önerilen limit','Risk ve getiri dengesi içinde politika sınırlarına uygun bulunan kredi tutarıdır.','Karar'],
 ['İkinci kontrol / Hassas karar','Makro stres senaryolarından en az birinde kararın değiştiğini gösterir. İnsan/risk yöneticisi kontrolü önerilir.','Risk'],
 ['Beklenen kazanç',helpData.expected_profit[1],'Ekonomi'],
 ['Beklenen zarar',helpData.expected_loss[1],'Risk'],
 ['RAROC',helpData.raroc[1],'Ekonomi'],
 ['EVPI',helpData.evpi[1],'Karar Bilimi'],
 ['EVSI',helpData.evsi[1],'Karar Bilimi'],
 ['Denetim izi',helpData.audit[1],'Yönetişim'],
 ['Karar Nasıl Alındı? raporu','Yönetici ve Risk Yöneticisi; girdiler, politika kontrolleri, ekonomik sonuçlar, alternatif aksiyonlar ve stres testini PDF olarak indirebilir.','Rapor']
];
const pageGuides={
  overview:{title:'Ana Panel · neye bakmalıyım?',summary:'Bu ekran günlük kredi operasyonunun kontrol merkezidir.',steps:['Yeni başvuru değerlendirmek için “Yeni Kredi Kararı”na geçin.','“İkinci kontrol” sayısı artıyorsa stres altında değişen kararları inceleyin.','Son kararlar tablosundan başvurunun ayrıntısını açın.'],terms:['stress','policy']},
  decision:{title:'Yeni Kredi Kararı · adım adım',summary:'Temel 5 bilgiyi girin; sistem politika, ekonomi, belirsizlik ve stres analizini birlikte çalıştırır.',steps:['Başvuru numarası ve talep tutarını girin.','PD ve LGD’yi yüzde olarak girin.','Aktif karar politikasını kullanın veya yetkiniz varsa uygun politikayı seçin.','“Kararı Hesapla”ya basın.','Önce ONAY/REDDET ve önerilen limiti; sonra “Neden?” ve stres sonucunu okuyun.'],terms:['amount','pd','lgd','policy','expected_profit','expected_loss','raroc','evsi','evpi','stress']},
  history:{title:'Başvurular · kayıt nasıl okunur?',summary:'Geçmiş kararları arayın, açın ve yetkiniz varsa yönetici karar raporunu indirin.',steps:['Arama alanına başvuru no, karar veya politika yazın.','“Aç” ile karar özetine gidin.','Yönetici/Risk Yöneticisi “PDF” ile kararın hesaplama raporunu alabilir.'],terms:['audit','policy','stress']},
  risk:{title:'Kredi Riski · neyi ölçer?',summary:'Tek kredi için temel risk ve sermaye ölçülerini görünür hale getirir.',steps:['Kullanılmış ve kullanılmamış limit ile CCF üzerinden EAD hesaplayın.','PD ve LGD ile beklenen kaybı hesaplayın.','Credit VaR, UL ve ekonomik sermayeyi birlikte okuyun.'],terms:['ead','ccf','unexpected_loss','credit_var','economic_capital']},
  governance:{title:'Politika & Yönetişim · kim kullanır?',summary:'Risk yöneticisi ve yönetici için kontrol, sürüm ve denetim merkezidir.',steps:['Aktif politika ve eşikleri kontrol edin.','Model sürümünü ve durumunu görün.','Yöneticiyseniz çalışan hesaplarını rol bazlı oluşturun.','Denetim izinden kritik işlemleri takip edin.'],terms:['policy','role','audit']},
  science:{title:'Gelişmiş Analizler · ne zaman gerekir?',summary:'Model geliştirme, validasyon ve karar bilimi analizleri için uzman ekranıdır.',steps:['Bayes ile yeni kanıt geldikçe olasılığı güncelleyin.','Normal karar aracıyla kritik oran / optimal miktarı inceleyin.','Karar Bilimi Haritasından motorun 16 teorik temelini görün.'],terms:['bayes','beta_prior','normal','evsi','evpi']}
};
const actionHelp={
  runDecision:'Girilen başvuruyu risk politikası, ekonomik değer, bilgi değeri ve stres senaryolarıyla değerlendirip kaydeder.',
  runSingleRisk:'EAD, EL, UL, Credit VaR ve ekonomik sermaye ölçülerini hesaplar.',
  refreshHistory:'Karar listesini sunucudan tekrar yükler.',
  refreshAudit:'Denetim olaylarını sunucudan tekrar yükler.',
  createUserBtn:'Yeni çalışan hesabı oluşturur. Kullanıcı ilk girişte geçici şifresini değiştirmek zorundadır.',
  runBayes:'Girdiğiniz önsel ve yeni gözlemlerle sonsal Beta dağılımını hesaplar.',
  runNormal:'Normal dağılım varsayımı altında kritik oran, z ve optimal miktarı hesaplar.'
};
function applyActionHelp(){
  Object.entries(actionHelp).forEach(([id,text])=>{const el=$(`#${id}`);if(el){el.title=text;el.setAttribute('aria-label',`${el.textContent.trim()}. ${text}`);}});
  $$('[data-help]').forEach(el=>{const x=helpData[el.dataset.help];if(x){el.title=x[0];if(!el.getAttribute('aria-label'))el.setAttribute('aria-label',`${x[0]} açıklamasını aç`);}});
}
function applyExplanationMode(){
  document.body.classList.toggle('explanations-off',!explanationsOn);
  const b=$('#explainModeBtn');if(b){b.textContent=explanationsOn?'Açıklamaları Gizle':'Açıklamaları Göster';b.setAttribute('aria-pressed',String(explanationsOn));}
}
function helpItem(title,text,category='Bilgi'){
  const item=node('button','help-item help-result');item.type='button';
  add(item,node('span','help-category',category),node('b','',title),node('span','',text));return item;
}
function renderPageHelp(){
  const content=$('#helpContent');clear(content);const guide=pageGuides[currentPage]||pageGuides.overview;
  const hero=node('div','help-focus page-help-focus');add(hero,node('span','help-category','BU EKRAN'),node('h4','',guide.title),node('p','',guide.summary));content.appendChild(hero);
  const steps=node('div','help-step-list');guide.steps.forEach((text,i)=>{const row=node('div','help-step-row');add(row,node('i','',i+1),node('span','',text));steps.appendChild(row);});content.appendChild(steps);
  const h=node('h4','help-section-title','Bu ekranda geçen önemli kavramlar');content.appendChild(h);
  guide.terms.forEach(key=>{const x=helpData[key];if(x){const item=helpItem(x[0],x[1],x[2]);item.onclick=()=>openHelp(key);content.appendChild(item);}});
}
function allGlossaryEntries(){
  const keyed=Object.entries(helpData).map(([key,x])=>({key,title:x[0],text:x[1],category:x[2]||'Bilgi'}));
  const extras=generalHelp.map((x,i)=>({key:`general-${i}`,title:x[0],text:x[1],category:x[2]||'Bilgi'}));
  return [...keyed,...extras].sort((a,b)=>a.title.localeCompare(b.title,'tr'));
}
function renderGlossary(query=''){
  const content=$('#helpContent');clear(content);const q=String(query||'').trim().toLocaleLowerCase('tr-TR');
  const entries=allGlossaryEntries().filter(x=>!q||`${x.title} ${x.text} ${x.category}`.toLocaleLowerCase('tr-TR').includes(q));
  const meta=node('div','glossary-meta',q?`${entries.length} eşleşme`:`${entries.length} kavram ve kullanım açıklaması`);content.appendChild(meta);
  if(!entries.length){const empty=node('div','empty-state');add(empty,node('b','','Sonuç bulunamadı'),node('span','','Daha kısa bir terim deneyin. Örn. “risk”, “PD” veya “faiz”.'));content.appendChild(empty);return;}
  entries.forEach(x=>content.appendChild(helpItem(x.title,x.text,x.category)));
}
function setHelpMode(mode){
  helpMode=mode;$('#helpPageTab')?.classList.toggle('active',mode==='page');$('#helpGlossaryTab')?.classList.toggle('active',mode==='glossary');
  if(mode==='page')renderPageHelp();else renderGlossary($('#helpSearch')?.value||'');
}
function openHelp(key=null){
  const d=$('#helpDrawer');$('#helpTitle').textContent=key&&helpData[key]?helpData[key][0]:'Yardım Merkezi';
  if(key&&helpData[key]){helpMode='glossary';const content=$('#helpContent');clear(content);const x=helpData[key];const focus=node('div','help-focus');add(focus,node('span','help-category',x[2]||'Bilgi'),node('h4','',x[0]),node('p','',x[1]));content.appendChild(focus);const back=node('button','btn secondary help-back','← Bu ekranın rehberine dön');back.onclick=()=>setHelpMode('page');content.appendChild(back);$('#helpPageTab')?.classList.remove('active');$('#helpGlossaryTab')?.classList.add('active');}
  else setHelpMode('page');
  d.classList.add('open');d.setAttribute('aria-hidden','false');$('#helpBackdrop').classList.remove('hidden');setTimeout(()=>$('#helpSearch')?.focus(),80);
}
function closeHelp(){ $('#helpDrawer').classList.remove('open');$('#helpDrawer').setAttribute('aria-hidden','true');$('#helpBackdrop').classList.add('hidden'); }
$('#helpBtn').onclick=()=>openHelp();$('#sideHelpBtn').onclick=()=>openHelp();$('#tourBtn').onclick=()=>{currentPage='overview';openHelp();};$('#closeHelp').onclick=closeHelp;$('#helpBackdrop').onclick=closeHelp;
$('#helpPageTab').onclick=()=>setHelpMode('page');$('#helpGlossaryTab').onclick=()=>setHelpMode('glossary');
$('#helpSearch').addEventListener('input',e=>{helpMode='glossary';$('#helpPageTab').classList.remove('active');$('#helpGlossaryTab').classList.add('active');renderGlossary(e.target.value);});
$('#explainModeBtn').onclick=()=>{explanationsOn=!explanationsOn;applyExplanationMode();};
$$('.info-btn,[data-help]').forEach(b=>{if(b.dataset.guidePage)return;b.onclick=(e)=>{e.preventDefault();openHelp(b.dataset.help||null);};});
$$('[data-guide-page]').forEach(b=>b.onclick=()=>{goToPage(b.dataset.guidePage);openHelp();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeHelp();if(e.key==='?'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){e.preventDefault();openHelp();}});

initMoneyInputs();
applyExplanationMode();
restoreSession();
