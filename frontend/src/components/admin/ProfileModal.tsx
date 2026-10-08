import React,{useState,useRef} from 'react';
import {Save,Upload,KeyRound} from 'lucide-react';
import {api,get,post,put,message} from '../../lib/api';
import {Btn,Field,Toggle} from '../shared';
import {toast} from 'sonner';

/** Shared profile editor for admin + storefront: name, photo upload, email,
 *  phone, change-password. Uses /auth/profile-extended + /auth/password/change
 *  + /customer/avatar. */
export const ProfileModal=({user,onDone}:{user:any;onDone:()=>void})=>{
 const [name,setName]=useState(user.name);
 const [email,setEmail]=useState(user.email);
 const [phone,setPhone]=useState(user.phone||'');
 const [avatar,setAvatar]=useState(user.avatar||'');
 const [pw,setPw]=useState({current:'',next:''});
 const fileRef=useRef<HTMLInputElement>(null);
 const busyRef=useState(false);
 const uploadAvatar=async(file:File)=>{
   const data=new FormData();data.append('file',file);
   try{const r:any=await api.post('/customer/avatar',data,{headers:{'Content-Type':'multipart/form-data'}});setAvatar(r.data.url);toast.success('Photo uploaded');}
   catch(e:any){toast.error(e?.response?.data?.detail||message(e));}
 };
 const saveProfile=async()=>{
   try{await put('/auth/profile-extended',{name,email,phone,avatar,current_password:pw.current});toast.success('Profile saved');onDone&&onDone();}
   catch(e:any){toast.error(e?.response?.data?.detail||message(e));}
 };
 const changePw=async()=>{
   try{const r=await post('/auth/password/change',{current_password:pw.current,new_password:pw.next});toast.success(r.note||'Password changed');setPw({current:'',next:''});}
   catch(e:any){toast.error(e?.response?.data?.detail||message(e));}
 };
 return <div data-testid="profile-editor">
  <div className="profile-avatar-row" style={{marginBottom:14}}>
   {avatar?<img src={avatar} alt="" className="profile-avatar-img"/>:<div className="profile-avatar-img profile-avatar-empty">{name.slice(0,1)}</div>}
   <Btn id="avatar-upload" variant="outline" onClick={()=>fileRef.current?.click()}><Upload size={15}/>Upload photo</Btn>
   <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e=>{const f=e.target.files?.[0];if(f)uploadAvatar(f);}}/>
  </div>
  <Field id="profile-name" label="Full name" required value={name} onChange={(e:any)=>setName(e.target.value)}/>
  <Field id="profile-email" label="Email" type="email" required value={email} onChange={(e:any)=>setEmail(e.target.value)}/>
  <Field id="profile-email-password" label="Current password (required to change email)" type="password" autoComplete="current-password" value={pw.current} onChange={(e:any)=>setPw({...pw,current:e.target.value})}/>
  <Field id="profile-phone" label="Phone" type="tel" value={phone} onChange={(e:any)=>setPhone(e.target.value)}/>
  <Btn id="profile-save" className="primary" onClick={saveProfile}><Save size={15}/>Save profile</Btn>
  <div style={{marginTop:22,paddingTop:16,borderTop:'1px solid var(--v-border)'}}>
   <h3 style={{margin:'0 0 10px',display:'flex',alignItems:'center',gap:8}}><KeyRound size={15}/>Change password</h3>
   <Field id="profile-pw-current" label="Current password" type="password" autoComplete="current-password" value={pw.current} onChange={(e:any)=>setPw({...pw,current:e.target.value})}/>
   <Field id="profile-pw-next" label="New password (10+ characters)" type="password" autoComplete="new-password" minLength={10} value={pw.next} onChange={(e:any)=>setPw({...pw,next:e.target.value})}/>
   <Btn id="profile-pw-save" variant="outline" disabled={!pw.current||pw.next.length<10} onClick={changePw}>Update password</Btn>
  </div>
 </div>;
};
export default ProfileModal;
