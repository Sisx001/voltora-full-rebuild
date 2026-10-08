import React, {useEffect, useRef, useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowRight, ArrowUpRight, Check, Copy, LockKeyhole, RefreshCw, ShoppingBag, WifiOff} from 'lucide-react';
import {Logo} from './store/Header';
import {useStore} from '../lib/store';
import {adminHref} from '../lib/adminPath';
import {StoreFailure} from '../lib/apiConfig';
import './store-recovery.css';

const descriptions: Record<StoreFailure['kind'], string> = {
  configuration: 'The store connection needs an owner configuration update. Retrying cannot replace missing settings.',
  offline: 'Your browser appears to be offline. Check your connection, then try reconnecting.',
  timeout: 'The store took too long to respond. Give it a moment, then try again.',
  network: 'We couldn’t connect to the store. Check your connection or try again in a moment.',
  server: 'The store couldn’t complete the last request. You can try again without starting over.',
  'invalid-response': 'The store returned an incomplete response. Please retry, or share the reference with the owner.',
};

export default function StoreRecovery() {
  const {error, configLoading, refreshConfig} = useStore();
  const failure = error as StoreFailure;
  const [online, setOnline] = useState(navigator.onLine);
  const [copyStatus, setCopyStatus] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    heading.current?.focus({preventScroll: true});
    const title = document.title;
    document.title = 'Reconnect to your store · VOLTORA';
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update); document.title = title; };
  }, []);
  useEffect(() => { setCopyStatus(''); }, [failure.reference]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(failure.reference); setCopyStatus('Reference copied'); }
    catch { setCopyStatus('Select and copy the reference shown above'); }
  };
  return <div className="store-recovery" data-testid="store-recovery">
    <header className="recovery-header"><Logo/><span className="recovery-header-note">THOUGHTFULLY CONNECTED.</span><span className="recovery-state"><span/>{online ? 'Connection interrupted' : 'Browser offline'}</span></header>
    <main className="recovery-main">
      <section className="recovery-copy" aria-labelledby="recovery-heading">
        <div className="recovery-eyebrow"><span/>A MOMENT TO RECONNECT</div>
        <h1 id="recovery-heading" ref={heading} tabIndex={-1}>A small pause.<br/><em>Not a lost bag.</em></h1>
        <p className="recovery-description">{online ? descriptions[failure.kind] : descriptions.offline}</p>
        <p className="recovery-promise">Reconnecting won’t clear your bag or local drafts.</p>
        <div className="recovery-actions">
          <button type="button" data-testid="retry-store" className="recovery-retry" disabled={configLoading || !online} onClick={refreshConfig}>
            <RefreshCw size={17} className={configLoading ? 'recovery-spinning' : ''}/>{configLoading ? 'Reconnecting…' : 'Reconnect to store'}<ArrowRight size={17}/>
          </button>
          <Link data-testid="store-recovery-admin" to={adminHref()} className="recovery-owner">Open owner workspace<ArrowUpRight size={16}/></Link>
        </div>
        <p className="recovery-feedback" role="status" aria-live="polite" aria-atomic="true">{configLoading ? 'Checking the store connection. Your saved items will not be changed.' : !online ? 'Reconnect is available when your browser is online.' : 'Your last connection attempt didn’t complete. Retry when you’re ready.'}</p>
        <details className="recovery-details">
          <summary>Connection details<span>For you & the store owner</span></summary>
          <div className="recovery-diagnostics">
            <span>{failure.serverReference ? 'Server error reference' : 'Local reference · no server reference received'}</span>
            <div className="recovery-reference"><code data-testid="recovery-reference">{failure.reference}</code><button type="button" onClick={copy} aria-label="Copy error reference" data-testid="copy-recovery-reference">{copyStatus === 'Reference copied' ? <Check size={16}/> : <Copy size={16}/>}</button></div>
            <p>{failure.status ? `HTTP ${failure.status} · ` : ''}{failure.kind.replace('-', ' ')} · <time dateTime={failure.occurredAt}>{new Date(failure.occurredAt).toLocaleTimeString()}</time></p>
            <p>Share this reference if the issue continues. Owner sign-in has its own connection checks; a store error does not sign you out.</p>
            {failure.kind === 'configuration' && <p data-testid="recovery-configuration-help">Owner setup: check REACT_APP_BACKEND_URL and the backend environment, then rebuild or restart. See docs/STARTUP.md.</p>}
            <span role="status">{copyStatus}</span>
          </div>
        </details>
      </section>
      <aside className="recovery-art" aria-label="Your place is kept">
        <div className="recovery-art-top"><span>THE EVERYDAY, UNINTERRUPTED.</span><span>01 / RECONNECT</span></div>
        <div className="recovery-orbit" aria-hidden="true"><div className="recovery-ring recovery-ring-one"/><div className="recovery-ring recovery-ring-two"/><div className="recovery-orbit-dot"/><div className="recovery-bag"><ShoppingBag strokeWidth={1} size={76}/><span><LockKeyhole size={14}/></span></div></div>
        <div className="recovery-art-copy"><span>NO NEED TO START OVER</span><h2>Your place.<br/>Kept for you.</h2><p>A connection retry is just that.<br/>Not a reset, not a new session.</p></div>
        <div className="recovery-art-footer"><LockKeyhole size={14}/><span>Nothing is cleared by reconnecting</span></div>
      </aside>
    </main>
    <footer className="recovery-footer"><span>VOLTORA <span>/</span> EVERY DETAIL, CONSIDERED.</span><span><WifiOff size={13}/>Connection status, not order status</span></footer>
  </div>;
}
