const $ = (id) => document.getElementById(id);
let selectedFiles = [];
let inspected = null;
let serviceOk = false;
const savedBase = localStorage.getItem('mintpack_api_base');
if (savedBase) $('apiBase').value = savedBase;

function apiBase(){ return $('apiBase').value.trim().replace(/\/$/, ''); }
function checkedApiBase(){
  const value=apiBase();
  let parsed;
  try { parsed=new URL(value); } catch (_) { throw new Error('نشانی سرویس معتبر نیست.'); }
  const local=['localhost','127.0.0.1','[::1]'].includes(parsed.hostname);
  if(parsed.protocol!=='https:' && !(local && parsed.protocol==='http:')) throw new Error('برای سرویس راه‌دور فقط HTTPS مجاز است.');
  if(parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error('نشانی سرویس نباید شامل اطلاعات ورود، query یا fragment باشد.');
  return value;
}
function apiHeaders(){ const key = $('apiKey').value.trim(); return key ? {'X-API-Key': key} : {}; }
function bytes(n){ if(n<1024)return n+' B'; if(n<1048576)return (n/1024).toFixed(1)+' KB'; return (n/1048576).toFixed(1)+' MB'; }
function updateBuildButton(){ $('buildBtn').disabled=!(serviceOk && selectedFiles.length && inspected); }
function setConnection(ok, message){ serviceOk=ok; $('connectionText').textContent=ok?'سرویس ساخت آماده است':'سرویس ساخت متصل نیست'; $('serviceStatus').textContent=message; updateBuildButton(); }
function showFiles(){
  $('fileList').innerHTML='';
  if(!selectedFiles.length){$('fileList').innerHTML='<span class="muted">هنوز فایلی انتخاب نشده است.</span>';$('inspectBtn').disabled=true;updateBuildButton();return;}
  selectedFiles.forEach(f=>{const row=document.createElement('div');row.className='file-item';const a=document.createElement('span');a.textContent=f.name;const b=document.createElement('span');b.textContent=bytes(f.size);row.append(a,b);$('fileList').append(row);});
  $('inspectBtn').disabled=false;updateBuildButton();
}
$('projectFiles').addEventListener('change',e=>{selectedFiles=Array.from(e.target.files||[]);inspected=null;$('previewWrap').classList.add('hidden');showFiles();$('inspectStatus').textContent='برای بررسی ساختار، پیش‌نمایش را اجرا کنید.';});
$('dropzone').addEventListener('dragover',e=>{e.preventDefault();$('dropzone').classList.add('dragover');});
$('dropzone').addEventListener('dragleave',()=> $('dropzone').classList.remove('dragover'));
$('dropzone').addEventListener('drop',e=>{e.preventDefault();$('dropzone').classList.remove('dragover');selectedFiles=Array.from(e.dataTransfer.files||[]);inspected=null;$('previewWrap').classList.add('hidden');$('inspectStatus').textContent='برای بررسی ساختار، پیش‌نمایش را اجرا کنید.';showFiles();});
async function uploadForm(url, extra={}){ const fd=new FormData();selectedFiles.forEach(f=>fd.append('project_files',f,f.name));Object.entries(extra).forEach(([k,v])=>fd.append(k,v));const r=await fetch(checkedApiBase()+url,{method:'POST',headers:apiHeaders(),body:fd});if(!r.ok)throw new Error((await r.text()).slice(0,500)||`HTTP ${r.status}`);return r.json(); }
$('apiBase').addEventListener('input',()=>{inspected=null;$('previewWrap').classList.add('hidden');setConnection(false,'نشانی سرویس تغییر کرده؛ دوباره اتصال را آزمایش کنید و پروژه را بررسی کنید.');});$('apiKey').addEventListener('input',()=>{inspected=null;$('previewWrap').classList.add('hidden');setConnection(false,'کلید سرویس تغییر کرده؛ دوباره اتصال را آزمایش کنید و پروژه را بررسی کنید.');});
$('testServiceBtn').addEventListener('click',async()=>{ $('serviceStatus').textContent='در حال بررسی...';try{const r=await fetch(checkedApiBase()+'/health',{headers:apiHeaders()});if(!r.ok)throw new Error('پاسخ نامعتبر '+r.status);const data=await r.json();if(data.status!=='ok')throw new Error('سرویس آماده نیست');localStorage.setItem('mintpack_api_base',apiBase());setConnection(true,'اتصال برقرار است · نسخه '+(data.version||'نامشخص'));}catch(e){setConnection(false,'خطا: '+e.message);}});
$('inspectBtn').addEventListener('click',async()=>{ $('inspectBtn').disabled=true;$('inspectStatus').textContent='در حال بررسی ZIP و مسیر index.html...';try{const data=await uploadForm('/api/inspect');inspected=data;$('inspectStatus').textContent='ساختار معتبر است. فایل ورودی: '+data.entrypoint;$('entryPath').textContent=data.entrypoint;$('previewFrame').src=apiBase()+data.preview_url;$('previewWrap').classList.remove('hidden');updateBuildButton();}catch(e){$('inspectStatus').textContent='خطا: '+e.message;}finally{$('inspectBtn').disabled=false;}});
function checked(id){return $(id).checked;}
function config(){
 const perms=[];if(checked('allowInternet'))perms.push('INTERNET');if(checked('networkState'))perms.push('ACCESS_NETWORK_STATE');if(checked('notifications'))perms.push('POST_NOTIFICATIONS');if(checked('vibrate'))perms.push('VIBRATE');if(checked('foregroundService')||checked('rubikaMode'))perms.push('FOREGROUND_SERVICE','FOREGROUND_SERVICE_DATA_SYNC');if(checked('bootReceiver')){perms.push('RECEIVE_BOOT_COMPLETED','POST_NOTIFICATIONS');}
 return {app_name:$('appName').value.trim(),package_name:$('packageName').value.trim(),version_name:$('versionName').value.trim(),version_code:Number($('versionCode').value),target_sdk:Number($('targetSdk').value),orientation:$('orientation').value,status_bar_color:$('statusBarColor').value,navigation_bar_color:$('navigationBarColor').value,full_screen:checked('fullScreen'),javascript_enabled:checked('javascriptEnabled'),offline_storage:checked('offlineStorage'),allow_internet:checked('allowInternet'),native_bridge:checked('nativeBridge'),rubika_mode:checked('rubikaMode'),permissions:perms};
}
$('nativeBridge').addEventListener('change',()=>{ $('bridgeWarning').style.display=checked('nativeBridge')?'block':'none'; });
$('rubikaMode').addEventListener('change',()=>{if(checked('rubikaMode')){$('foregroundService').checked=true;$('notifications').checked=true;$('nativeBridge').checked=true;$('allowInternet').checked=true;}});
$('bootReceiver').addEventListener('change',()=>{if(checked('bootReceiver'))$('notifications').checked=true;});
function validConfig(c){if(!c.app_name||!c.package_name||!c.version_name)throw new Error('نام، شناسه بسته و نسخه الزامی هستند.');if(!/^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*){1,}$/.test(c.package_name))throw new Error('Package Name معتبر نیست.');if(!Number.isInteger(c.version_code)||c.version_code<1)throw new Error('کد نسخه باید عدد صحیح مثبت باشد.');if(c.native_bridge&&!c.allow_internet)throw new Error('برای فراخوانی API، دسترسی اینترنت لازم است.');if(c.rubika_mode&&!c.permissions.includes('FOREGROUND_SERVICE_DATA_SYNC'))throw new Error('مجوز سرویس پیش‌زمینه انتخاب نشده است.');}
$('buildBtn').addEventListener('click',async()=>{
 try{
   if(!inspected)throw new Error('ابتدا پروژه را بررسی و پیش‌نمایش کنید.');
   const c=config();validConfig(c);const keyFile=$('keystoreFile').files[0];if(!keyFile)throw new Error('برای ساخت Release، فایل keystore لازم است.');if(!$('keyAlias').value.trim()||!$('storePassword').value||!$('keyPassword').value)throw new Error('اطلاعات امضای APK کامل نیست.');
   const fd=new FormData();selectedFiles.forEach(f=>fd.append('project_files',f,f.name));fd.append('config',JSON.stringify(c));fd.append('keystore',keyFile,keyFile.name);const icon=$('appIcon').files[0];if(icon)fd.append('app_icon',icon,icon.name);const splash=$('splashImage').files[0];if(splash)fd.append('splash_image',splash,splash.name);fd.append('key_alias',$('keyAlias').value.trim());fd.append('store_password',$('storePassword').value);fd.append('key_password',$('keyPassword').value);
   $('buildBtn').disabled=true;$('downloadLink').classList.add('hidden');$('progress').classList.remove('hidden');$('progressBar').style.width='8%';$('buildStatus').textContent='در حال ارسال پروژه به موتور ساخت...';
   const r=await fetch(checkedApiBase()+'/api/build',{method:'POST',headers:apiHeaders(),body:fd});if(!r.ok)throw new Error((await r.text()).slice(0,500));const job=await r.json();if(!job.job_id)throw new Error('شناسه Job از سرویس دریافت نشد.');
   let done=false;while(!done){await new Promise(resolve=>setTimeout(resolve,1800));const s=await fetch(checkedApiBase()+'/api/jobs/'+encodeURIComponent(job.job_id),{headers:apiHeaders()});if(!s.ok)throw new Error('خطا در دریافت وضعیت ساخت');const st=await s.json();$('buildStatus').textContent=st.message||st.status;$('progressBar').style.width=Math.max(12,Math.min(95,st.progress||15))+'%';if(st.status==='succeeded'){done=true;$('progressBar').style.width='100%';$('downloadLink').href=checkedApiBase()+st.download_url;$('downloadLink').classList.remove('hidden');$('buildStatus').textContent='ساخت و اعتبارسنجی APK با موفقیت انجام شد.';}else if(st.status==='failed'){throw new Error(st.message||'ساخت ناموفق بود');}}
 }catch(e){$('buildStatus').textContent='خطا: '+e.message;$('progressBar').style.width='0%';}finally{updateBuildButton();}
});

$('downloadLink').addEventListener('click',async(e)=>{e.preventDefault();try{const r=await fetch($('downloadLink').href,{headers:apiHeaders()});if(!r.ok)throw new Error('دانلود APK ناموفق بود');const blob=await r.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='MintPack-output.apk';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}catch(err){$('buildStatus').textContent='خطای دانلود: '+err.message;}});
