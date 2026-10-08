import React,{useEffect,useRef,useState} from 'react';
import {useStore} from '../../lib/store';
export const LivePageFrame=({draft,device}:any)=>{const frame=useRef<HTMLIFrameElement>(null),area=useRef<HTMLDivElement>(null),latest=useRef(draft);const [zoom,setZoom]=useState(1);const {config}=useStore();latest.current=draft;const width=device==='mobile'?390:device==='tablet'?768:1440;
const push=()=>frame.current?.contentWindow?.postMessage({type:'voltora-page-preview',page:latest.current},window.location.origin);
useEffect(()=>{push();},[draft]);useEffect(()=>{const node=area.current;if(!node)return;const resize=()=>setZoom(Math.min(1,node.clientWidth/width));resize();const ro=new ResizeObserver(resize);ro.observe(node);return()=>ro.disconnect();},[width]);
useEffect(()=>{const receive=(e:MessageEvent)=>{if(e.origin===window.location.origin&&e.source===frame.current?.contentWindow&&e.data?.type==='voltora-preview-ready')push();};window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);},[]);
const src=(draft.slug==='home'?'/':'/pages/'+draft.slug)+'?theme_preview='+config.theme.id;
return <div className="actual-page-canvas" ref={area}><div className="preview-browser"><span/><span/><span/><b>EXACT PAGE · LIVE DRAFT · READ-ONLY PREVIEW</b></div><div style={{height:650,overflow:'hidden',position:'relative'}}><iframe name="voltora-preview" sandbox="allow-scripts allow-same-origin" title="Exact page live preview" data-testid="builder-live-preview" ref={frame} src={src} style={{width,height:650/zoom,transform:`scale(${zoom})`,transformOrigin:'top left',border:0}} onLoad={push}/></div></div>;
};
