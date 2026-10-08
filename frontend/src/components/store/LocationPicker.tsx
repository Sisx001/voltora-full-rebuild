import React,{useEffect,useRef,useState} from 'react';
import {MapPin,Search,Sparkles,Loader2} from 'lucide-react';
import {get,post,message} from '../../lib/api';

export interface LocationValue{division_id:string;district_id:string;upazila_id:string;area_id:string;postcode:string}

const empty:LocationValue={division_id:'',district_id:'',upazila_id:'',area_id:'',postcode:''};

/** Structured Bangladesh address picker: Division → District → Upazila/Thana → Area (postcode),
 *  with ranked search and an optional AI-assisted "smart" resolve (search only, no chat). */
export const LocationPicker=({value,onChange,testPrefix='location'}:{value:LocationValue;onChange:(v:LocationValue)=>void;testPrefix?:string})=>{
 const [tree,setTree]=useState<any[]>([]),[districts,setDistricts]=useState<any[]>([]);
 const [children,setChildren]=useState<{upazilas:any[];areas:any[]}>({upazilas:[],areas:[]});
 const [q,setQ]=useState(''),[results,setResults]=useState<any[]>([]),[searching,setSearching]=useState(false),[showResults,setShowResults]=useState(false);
 const [smartBusy,setSmartBusy]=useState(false),[smart,setSmart]=useState<any[]|null>(null);
 const [openDistrict,setOpenDistrict]=useState('');
 const boxRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{get('/locations/tree').then((d:any)=>{setTree(d.divisions);setDistricts(d.divisions.flatMap((x:any)=>x.districts));}).catch(()=>{});},[]);
 const loadChildren=async(districtId:string)=>{if(!districtId){setChildren({upazilas:[],areas:[]});setOpenDistrict('');return {upazilas:[],areas:[]};}setOpenDistrict(districtId);try{const d=await get('/locations/districts/'+districtId+'/children');const next={upazilas:d.upazilas||[],areas:d.areas||[]};setChildren(next);return next;}catch(e){setChildren({upazilas:[],areas:[]});return {upazilas:[],areas:[]};}};
 useEffect(()=>{if(value.district_id&&value.district_id!==openDistrict)loadChildren(value.district_id);},[value.district_id]);
 const set=(patch:Partial<LocationValue>)=>{const next={...value,...patch};if(!next.postcode){const area=children.areas.find((a:any)=>a.id===next.area_id);if(area?.postcode)next.postcode=area.postcode;}onChange(next);};
 const pickDistrict=(id:string)=>{const district=districts.find((d:any)=>d.id===id);set({district_id:id,upazila_id:'',area_id:'',postcode:''});if(district)loadChildren(id);};
 useEffect(()=>{if(q.trim().length<2){setResults([]);return;}setSearching(true);const t=setTimeout(async()=>{try{const rows=await get('/locations/search?q='+encodeURIComponent(q.trim()));setResults(rows);setShowResults(true);}catch(e){setResults([]);}finally{setSearching(false);}},250);return()=>clearTimeout(t);},[q]);
 const applyResult=async(row:any)=>{
  const patch:LocationValue={...empty};
  if(row.kind==='district'){patch.division_id=row.parent_id;patch.district_id=row.id;}
  else if(row.kind==='upazila'){const district=districts.find((d:any)=>d.id===row.district_id||row.id.startsWith(d.id.replace('dis:','')));if(row.parent_id?.startsWith('dis:'))patch.district_id=row.parent_id;else if(district)patch.district_id=district.id;const dis=districts.find((d:any)=>d.id===patch.district_id);if(dis)patch.division_id=dis.parent_id;patch.upazila_id=row.id;}
  else if(row.kind==='area'){patch.area_id=row.id;patch.postcode=row.postcode||'';if(row.upazila_id)patch.upazila_id=row.upazila_id;if(row.district_id){patch.district_id=row.district_id;const dis=districts.find((d:any)=>d.id===row.district_id);if(dis)patch.division_id=dis.parent_id;}}
  if(patch.district_id){const next=await loadChildren(patch.district_id);if(patch.area_id&&!patch.postcode){const area=next.areas.find((a:any)=>a.id===patch.area_id);if(area?.postcode)patch.postcode=area.postcode;}}
  onChange(patch);setQ('');setShowResults(false);setSmart(null);
 };
 const smartResolve=async()=>{setSmartBusy(true);try{const d=await post('/locations/resolve',{query:q.trim()});setSmart(d.candidates||[]);setShowResults(false);}catch(e){setSmart([]);const msg=message(e);}finally{setSmartBusy(false);}};
 useEffect(()=>{const close=(e:any)=>{if(boxRef.current&&!boxRef.current.contains(e.target))setShowResults(false);};document.addEventListener('mousedown',close);return()=>document.removeEventListener('mousedown',close);},[]);
 const division=tree.find((d:any)=>d.id===value.division_id);
 const district=districts.find((d:any)=>d.id===value.district_id);
 const upazila=children.upazilas.find((u:any)=>u.id===value.upazila_id);
 const area=children.areas.find((a:any)=>a.id===value.area_id);
 const areaOptions=value.upazila_id?children.areas.filter((a:any)=>a.upazila_id===value.upazila_id||a.parent_id===value.upazila_id):children.areas;
 return <div className="location-picker" ref={boxRef}>
  <div className="location-search">
   <Search size={16}/>
   <input data-testid={`${testPrefix}-search`} placeholder="Search division, district, area, or postcode..." value={q} onChange={e=>setQ(e.target.value)} onFocus={()=>{if(results.length)setShowResults(true);}}/>
   {searching&&<Loader2 size={15} className="spin"/>}
   {q.trim().length>=2&&<button type="button" className="location-smart" data-testid={`${testPrefix}-smart`} title="Smart address lookup" disabled={smartBusy} onClick={smartResolve}>{smartBusy?<Loader2 size={14} className="spin"/>:<Sparkles size={14}/>}Smart find</button>}
  </div>
  {showResults&&results.length>0&&<div className="location-results" data-testid={`${testPrefix}-results`}>{results.map((r:any)=><button type="button" key={r.id} onClick={()=>applyResult(r)}><MapPin size={14}/><span><b>{r.name}</b><small>{r.kind==='area'?[r.thana,r.postcode].filter(Boolean).join(' · '):r.kind==='district'?'District':r.kind==='upazila'?'Upazila / Thana':'Division'}</small></span></button>)}</div>}
  {smart&&<div className="location-results">{smart.length?smart.map((r:any)=><button type="button" key={r.id} onClick={()=>{applyResult(r);}}><Sparkles size={14}/><span><b>{r.name}</b><small>{[r.thana,r.postcode].filter(Boolean).join(' · ')} · confidence {Math.round((r.confidence||0.5)*100)}%</small></span></button>):<p className="small-note" style={{padding:'10px 14px'}}>No confident match. Try a district, upazila, or postcode.</p>}</div>}
  <div className="location-cascades">
   <select data-testid={`${testPrefix}-division`} aria-label="Division" value={value.division_id} onChange={e=>{const div=tree.find(d=>d.id===e.target.value);onChange({...empty,division_id:e.target.value});setChildren({upazilas:[],areas:[]});setOpenDistrict('');}}>
    <option value="">Division</option>
    {tree.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}
   </select>
   <select data-testid={`${testPrefix}-district`} aria-label="District" value={value.district_id} disabled={!value.division_id} onChange={e=>pickDistrict(e.target.value)}>
    <option value="">District</option>
    {(division?.districts||[]).map((d:any)=><option key={d.id} value={d.id}>{d.name}</option>)}
   </select>
   <select data-testid={`${testPrefix}-upazila`} aria-label="Upazila or Thana" value={value.upazila_id} disabled={!value.district_id} onChange={e=>set({upazila_id:e.target.value,area_id:''})}>
    <option value="">Upazila / Thana (optional)</option>
    {children.upazilas.map(u=><option key={u.id} value={u.id}>{u.name}</option>)}
   </select>
   <select data-testid={`${testPrefix}-area`} aria-label="Post office area" value={value.area_id} disabled={!value.district_id} onChange={e=>{const a=children.areas.find(x=>x.id===e.target.value);set({area_id:e.target.value,postcode:a?.postcode||''});}}>
    <option value="">Area / post office (optional)</option>
    {areaOptions.map((a:any)=><option key={a.id} value={a.id}>{a.name}{a.postcode?' · '+a.postcode:''}</option>)}
   </select>
   <input data-testid={`${testPrefix}-postcode`} placeholder="Postcode" maxLength={10} value={value.postcode} onChange={e=>set({postcode:e.target.value})}/>
  </div>
  {(division||district||upazila||area)&&<p className="small-note location-summary">{[district?.name||division?.name,upazila?.name,area?.name].filter(Boolean).join(' → ')}{value.postcode?' · '+value.postcode:''}</p>}
 </div>;
};
export default LocationPicker;
