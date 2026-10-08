/** Configurable admin entry path (build-time). Changing the URL is a convenience
 * measure, never a security control - authentication, MFA and RBAC protect the admin. */
export const ADMIN_PATH = process.env.REACT_APP_ADMIN_PATH || '/admin';
export const adminHref=(path='')=>ADMIN_PATH+(path?'/'+path:'');
