/** Configurable admin entry path (build-time). Changing the URL is a convenience
 * measure, never a security control - authentication, MFA and RBAC protect the admin. */
const configuredPath = (process.env.REACT_APP_ADMIN_PATH || '/admin').replace(/\/+$/, '');
export const ADMIN_PATH = /^\/[A-Za-z0-9_-]+(?:\/[A-Za-z0-9_-]+)*$/.test(configuredPath) ? configuredPath : '/admin';
export const adminHref=(path='')=>ADMIN_PATH+(path?'/'+path.replace(/^\/+/, ''):'');
export const isAdminPath=(pathname:string)=>pathname===ADMIN_PATH||pathname.startsWith(ADMIN_PATH+'/');
