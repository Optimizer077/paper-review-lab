const $ = s => document.querySelector(s);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {'guide':'Guide','course':'Course','book':'Book / manual','reporting-guideline':'Reporting guideline','documentation':'Documentation','tool':'Tool'};
const accessLabels = {'open-web':'Open web','mixed':'Mixed access','book-or-library':'Book or library access','institutional-or-paid':'Institutional or paid access','open-source':'Open source'};
const levels = {'page-content':'Primary page content checked','publisher-metadata':'Publisher metadata checked; book not inspected','author-metadata':'Author book information checked; book not inspected','source-code-documentation':'Official documentation checked','indexed-primary-excerpt':'Indexed primary excerpt checked; direct retrieval limited'};
let catalog, records = [], filtered = [], page = 0;
const size = 10;
function safeUrl(value){try{const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password?url.href:'#directory';}catch{return '#directory';}}
function render(){
  const pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages-1);
  $('#resource-count').textContent=`${filtered.length} of ${records.length} resources`;
  $('#resource-page').textContent=`${page+1} / ${pages}`;
  $('#resource-prev').disabled=page===0;$('#resource-next').disabled=page>=pages-1;
  $('#resource-rows').innerHTML=filtered.slice(page*size,(page+1)*size).map(r=>`<article class="support-row"><span class="support-number">${String(r._index).padStart(2,'0')}</span><div><div class="support-meta">${escape(catalog.categories[r.category])}</div><h3><a href="${escape(safeUrl(r.url))}" target="_blank" rel="noopener">${escape(r.title)} ↗</a></h3><div class="support-meta">${escape(r.provider)} · ${escape(labels[r.resource_type])}<br>${escape(accessLabels[r.access])}</div><p>${escape(r.summary)}</p>${r.resource_type==='book'?'<span class="inspection-tag">BOOK INFORMATION ONLY</span>':''}</div><div class="support-detail"><p class="support-use"><strong>Use it for:</strong> ${escape(r.how_to_use)}</p><details><summary>Scope, limits and source check</summary><p><strong>Limits:</strong> ${escape(r.limits)}</p><p>${escape(r.source_note)}</p><span class="inspection-tag">${escape(levels[r.inspection_level])} · ${escape(r.verified_at)}</span><p><a href="${escape(safeUrl(r.verification_url))}" target="_blank" rel="noopener">Open the checked source ↗</a></p></details></div></article>`).join('')||'<p class="support-empty">No resources match these filters. Try another task or clear the filters.</p>';
}
function filter(){
  const term=$('#resource-search').value.toLocaleLowerCase().trim(),category=$('#resource-category').value,type=$('#resource-type').value,profile=$('#resource-profile').value;
  filtered=records.filter(r=>(!term||r._search.includes(term))&&(!category||r.category===category)&&(!type||r.resource_type===type)&&(!profile||r.profiles.includes(profile)));page=0;render();
}
async function init(){
  try{
    const response=await fetch(new URL('./data/writing-resources.json',import.meta.url));if(!response.ok)throw new Error(`Catalog unavailable (${response.status}).`);catalog=await response.json();
    records=catalog.resources.map((r,i)=>({...r,_index:i+1,_search:[r.title,r.provider,r.summary,r.how_to_use,...r.tasks,...r.tags].join(' ').toLocaleLowerCase()}));
    $('#resource-total').textContent=records.length;
    $('#resource-category').innerHTML='<option value="">All categories</option>'+Object.entries(catalog.categories).map(([id,title])=>`<option value="${escape(id)}">${escape(title)}</option>`).join('');
    $('#resource-type').innerHTML='<option value="">All types</option>'+[...new Set(records.map(r=>r.resource_type))].map(id=>`<option value="${escape(id)}">${escape(labels[id])}</option>`).join('');
    $('#starter-links').innerHTML=catalog.starter_ids.map((id,i)=>records.find(r=>r.id===id)).filter(Boolean).map((r,i)=>`<a href="${escape(safeUrl(r.url))}" target="_blank" rel="noopener"><span>0${i+1}</span>${escape(r.title)} ↗</a>`).join('');
    $('#checked-date').textContent=`Catalog updated ${catalog.updated_at}. Access and policies can change; inspect the original source.`;
    for(const id of ['resource-search','resource-category','resource-type','resource-profile'])$(`#${id}`).addEventListener(id==='resource-search'?'input':'change',filter);
    $('#clear-resources').addEventListener('click',()=>{for(const id of ['resource-search','resource-category','resource-type','resource-profile'])$(`#${id}`).value='';filter();});
    $('#resource-prev').addEventListener('click',()=>{page--;render();});$('#resource-next').addEventListener('click',()=>{page++;render();});
    const category=new URLSearchParams(location.search).get('category');if(category&&catalog.categories[category])$('#resource-category').value=category;
    filter();
  }catch(error){$('#resource-error').hidden=false;$('#resource-error').textContent=`${error.message} Use the catalog in the GitHub toolkit if this page cannot load.`;$('#resource-count').textContent='Catalog could not load.';}
}
init();
