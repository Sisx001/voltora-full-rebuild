'''Permission domains, built-in roles, and the authorize gate.

Permission strings are 'domain.action'. Built-in roles are defined here;
custom roles live in the `roles` collection and are resolved at session
creation (permissions are embedded in the session doc, so a permission
change requires revoking that role's sessions - handled by roles.py).
'''
from fastapi import HTTPException, Depends
from core import db, audit

DOMAINS = ['mail', 'integrations', 'products', 'catalog', 'inventory', 'orders', 'customers', 'coupons', 'payments', 'shipping', 'content', 'theme', 'media', 'support', 'settings', 'roles', 'security', 'audit', 'analytics', 'ai', 'couriers', 'locations', 'returns', 'loyalty', 'notifications', 'marketing']
VERBS = ['read', 'update', 'publish', 'export', 'refund']
ALL = [f'{d}.{a}' for d in DOMAINS for a in VERBS]

BUILT_IN_ROLES = {
    'owner': ALL,
    'super_admin': ALL,
    'admin': [p for p in ALL if not p.startswith(('roles.', 'security.'))],
    'store_manager': [p for p in ALL if not p.startswith(('roles.', 'security.'))],
    'moderator': ['support.read', 'support.update', 'products.read', 'products.publish', 'orders.read', 'customers.read', 'audit.read', 'content.read'],
    'product_manager': ['products.read', 'products.update', 'products.publish', 'products.export', 'catalog.read', 'catalog.update', 'inventory.read', 'inventory.update', 'media.read', 'media.update', 'ai.read', 'ai.update', 'locations.read'],
    'seller': ['products.read', 'products.update', 'inventory.read', 'inventory.update', 'orders.read', 'customers.read'],
    'order_manager': ['orders.read', 'orders.update', 'orders.export', 'customers.read', 'inventory.read', 'support.read', 'support.update', 'couriers.read', 'couriers.update', 'returns.read', 'returns.update'],
    'finance_manager': ['orders.read', 'orders.export', 'payments.read', 'payments.update', 'payments.refund', 'analytics.read', 'returns.read', 'returns.update', 'loyalty.read'],
    'content_editor': ['content.read', 'content.update', 'content.publish', 'theme.read', 'theme.update', 'theme.publish', 'media.read', 'media.update', 'catalog.read', 'products.read'],
    'support_agent': ['support.read', 'support.update', 'orders.read', 'customers.read', 'returns.read'],
    'marketing_manager': ['marketing.read', 'marketing.update', 'content.read', 'content.update', 'catalog.read', 'products.read', 'analytics.read', 'coupons.read', 'coupons.update', 'notifications.read', 'notifications.update', 'ai.read'],
    'inventory_manager': ['inventory.read', 'inventory.update', 'products.read', 'catalog.read', 'orders.read', 'locations.read'],
    'seo_manager': ['products.read', 'products.update', 'content.read', 'content.update', 'analytics.read', 'marketing.read', 'locations.read'],
    'analyst': ['analytics.read', 'orders.export', 'loyalty.read', 'ai.read'],
    'investor': [p for p in ALL if p.endswith('.read') and not p.startswith(('security.', 'roles.'))],
 'designer': ['content.read','content.update','content.publish','theme.read','theme.update','theme.publish','media.read','media.update','catalog.read'],
    'customer': []
}
ROLE_IDS = [r for r in BUILT_IN_ROLES if r not in ('owner', 'customer')]
# backwards-compatible alias used by existing modules
ROLES = BUILT_IN_ROLES


async def role_permissions(role):
    '''Resolve a role id to its permission list (built-in first, then DB custom roles).'''
    if role in BUILT_IN_ROLES:
        return BUILT_IN_ROLES[role]
    row = await db.roles.find_one({'id': role}, {'_id': 0, 'permissions': 1})
    return (row or {}).get('permissions', [])


def permissions(user):
    '''Sync resolution for users whose permissions were embedded by the session loader.'''
    value = user.get('permissions') if isinstance(user.get('permissions'), list) else None
    return value if value is not None else BUILT_IN_ROLES.get(user.get('role'), [])


async def authorize(user, action):
    if action.split('.')[-1] != 'read' and user.get('role') == 'investor':
        raise HTTPException(403, 'Investor access is read-only')
    if user.get('role') != 'customer' and not user.get('session_mfa'):
        raise HTTPException(403, 'Complete two-factor authentication to access the workspace')
    if action not in permissions(user):
        await audit(user, 'authorization.denied', action)
        raise HTTPException(403, 'You do not have permission for this action')


def require(action):
    from auth import current_user
    async def dependency(user=Depends(current_user)):
        await authorize(user, action)
        return user
    return dependency
