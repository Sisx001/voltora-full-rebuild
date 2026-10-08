import React,{useState,useEffect} from 'react';
import {Plus,Search,Trash2,Edit3,Upload,MapPin} from 'lucide-react';
import {api,get,post,put,message} from '../../lib/api';
import {PageTitle,Btn,Field,Loading,Empty,Toggle,Modal,Status} from '../../components/shared';
import {toast} from 'sonner';

const KINDS=[['division','Divisions'],['district','Districts'],['upazila','Upazilas'],['area','Areas & postcodes']] as const;

export const AdminLocations=()=>{
 const [kind,setKind]=useState('district'),[q,setQ]=useState(''),[page,setPage]=useState(1),[data,setData]=useState<any>(null),[edit,setEdit]=useState<any>(null),[importOpen,setImportOpen]=useState(false),[importText,setImportText]=useState('');
 const load=()=>get(`/admin/locations?kind=${kind}&q=${encodeURIComponent(q)}&page=${page}`).then(setData).catch(e=>toast.error(message(e)));
 useEffect(()=>{load();},[kind,q,page]);
 const save=async()=>{try{edit.id?await put('/admin/locations/'+edit.id,{kind:edit.kind,parent_id:edit.parent_id||'',name:edit.name,name_bn:edit.name_bn||'',postcode:edit.postcode||'',active:edit.active!==false}):await post('/admin/locations',{kind:edit.kind,parent_id:edit.parent_id||'',name:edit.name,name_bn:edit.name_bn||'',postcode:edit.postcode||'',active:edit.active!==false});setEdit(null);load();toast.success('Location saved');}catch(e){toast.error(message(e));}};
 const toggle=async(row:any)=>{try{await post('/admin/locations/'+row.id+'/toggle');load();}catch(e){toast.error(message(e));}};
 const remove=async(row:any)=>{try{await api.delete('/admin/locations/'+row.id);load();toast.success('Location removed');}catch(e){toast.error(message(e));}};
 const runImport=async()=>{try{let items:any[];try{items=JSON.parse(importText);}catch(e){throw new Error('The import payload is not valid JSON');}const r=await post('/admin/locations/import',{items});setImportOpen(false);setImportText('');load();toast.success(`${r.imported} imported, ${r.skipped} skipped`);}catch(e){toast.error(e.message||message(e));}};
 return <><PageTitle eyebrow="CATALOG / LOCATIONS" title="Every corner of Bangladesh, organized." description="The delivery hierarchy customers pick at checkout. Deactivated entries stay in orders but disappear from selection."><Btn id="location-import" variant="outline" onClick={()=>setImportOpen(true)}><Upload size={16}/>Import JSON</Btn><Btn id="location-add" className="primary" onClick={()=>setEdit({kind,parent_id:'',name:'',name_bn:'',postcode:'',active:true})}><Plus size={16}/>Add location</Btn></PageTitle>
 <div className="admin-panel">
  <div className="table-toolbar"><div className="table-tabs">{KINDS.map(([id,label])=><button data-testid={`locations-kind-${id}`} key={id} className={kind===id?'active':''} onClick={()=>{setKind(id);setPage(1);}}>{label}</button>)}</div><div className="table-search"><Search size={16}/><input data-testid="locations-search" placeholder="Search name, Bangla name, or postcode..." value={q} onChange={e=>{setQ(e.target.value);setPage(1);}}/></div></div>
  {!data?<Loading/>:data.items.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Name</th><th>Bangla</th><th>Postcode</th><th>Parent</th><th>Status</th><th/></tr></thead><tbody>{data.items.map((row:any)=><tr key={row.id}><td><b>{row.name}</b><small className="block mono">{row.id}</small></td><td>{row.name_bn||'—'}</td><td className="mono">{row.postcode||'—'}</td><td className="mono" style={{fontSize:11}}>{row.parent_id||'—'}</td><td><Status id={`location-status-${row.id}`} value={row.active?'published':'disabled'}/></td><td><button data-testid={`location-edit-${row.id}`} className="icon-btn" title="Edit" onClick={()=>setEdit({...row})}><Edit3 size={15}/></button><button data-testid={`location-toggle-${row.id}`} className="icon-btn" title="Activate / deactivate" onClick={()=>toggle(row)}><MapPin size={15}/></button><button data-testid={`location-delete-${row.id}`} className="icon-btn" title="Delete" onClick={()=>remove(row)}><Trash2 size={15}/></button></td></tr>)}</tbody></table></div>:<Empty icon={MapPin} title="Nothing here yet." description="Try a different search, or add a location."/>}
  {data&&data.total>100&&<div className="table-toolbar" style={{justifyContent:'center'}}><Btn id="locations-prev" variant="outline" disabled={page<=1} onClick={()=>setPage(page-1)}>Previous</Btn><span className="small-note">Page {page} of {Math.ceil(data.total/100)}</span><Btn id="locations-next" variant="outline" disabled={page>=Math.ceil(data.total/100)} onClick={()=>setPage(page+1)}>Next</Btn></div>}
 </div>
 <Modal open={!!edit} onClose={()=>setEdit(null)} title={edit?.id?'Edit location':'Add a location'} description="Renaming and deactivating are safe for existing orders — they store their own copy.">{edit&&<form onSubmit={e=>{e.preventDefault();save();}}>
  <Field id="location-kind" label="Type" as="select" value={edit.kind} onChange={(e:any)=>setEdit({...edit,kind:e.target.value})}>{KINDS.map(([id,label])=><option key={id} value={id}>{label}</option>)}</Field>
  {edit.kind!=='division'&&<Field id="location-parent" label="Parent location id (e.g. dis:dhaka)" required value={edit.parent_id||''} onChange={(e:any)=>setEdit({...edit,parent_id:e.target.value})}/>}
  <Field id="location-name" label="Name (English)" required value={edit.name||''} onChange={(e:any)=>setEdit({...edit,name:e.target.value})}/>
  <Field id="location-name-bn" label="Name (Bangla)" value={edit.name_bn||''} onChange={(e:any)=>setEdit({...edit,name_bn:e.target.value})}/>
  {edit.kind==='area'&&<Field id="location-postcode" label="Postcode" value={edit.postcode||''} onChange={(e:any)=>setEdit({...edit,postcode:e.target.value})}/>}
  <Toggle id="location-active" label="Available to customers" value={edit.active!==false} onChange={(v:boolean)=>setEdit({...edit,active:v})}/>
  <Btn id="location-save" type="submit" className="primary">Save location</Btn></form>}</Modal>
 <Modal open={importOpen} onClose={()=>setImportOpen(false)} title="Bulk import locations" description="Paste a JSON array of {kind, parent_id, name, name_bn?, postcode?}. Rows with existing ids are skipped.">
  <Field id="location-import-json" label="JSON payload" as="textarea" rows={10} value={importText} onChange={(e:any)=>setImportText(e.target.value)}/>
  <Btn id="location-import-run" className="primary" onClick={runImport}><Upload size={15}/>Import</Btn></Modal></>;
};
export default AdminLocations;
