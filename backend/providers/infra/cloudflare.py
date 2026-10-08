'''Cloudflare integration: real API-token verification and live zone actions
(purge cache, development mode). Uses httpx against api.cloudflare.com — no
simulated responses. The API token is a write-only, Fernet-sealed credential.'''
import httpx
from providers.base import InfraProvider, register_infra, ProviderError, field, setting

API = 'https://api.cloudflare.com/client/v4'


@register_infra
class CloudflareInfra(InfraProvider):
    id = 'cloudflare'
    label = 'Cloudflare'
    docs_url = 'https://developers.cloudflare.com/api/'
    actions = ['purge_cache', 'dev_mode']
    config_fields = [
        field('api_token', 'API token', secret=True, help='Create a token with Zone.Cache Purge and Zone Settings edit permissions.'),
    ]
    settings_fields = [
        setting('zone_id', 'Zone ID', help='From the Cloudflare domain overview page. Required for actions.'),
        setting('zone_name', 'Zone name (your domain)', required=False, placeholder='example.com'),
    ]

    async def _client(self, credentials: dict) -> httpx.AsyncClient:
        token = (credentials or {}).get('api_token', '')
        if not token:
            raise ProviderError('Save a Cloudflare API token first')
        return httpx.AsyncClient(base_url=API, headers={'Authorization': f'Bearer {token}'}, timeout=20)

    @staticmethod
    def _raise_for_cloudflare(payload: dict) -> dict:
        if not payload.get('success'):
            errors = '; '.join(e.get('message', 'unknown error') for e in payload.get('errors', []))
            raise ProviderError(f'Cloudflare API rejected the call: {errors[:300]}')
        return payload

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        try:
            async with await self._client(credentials) as client:
                r = await client.get('/zones', params={'per_page': 5})
                payload = r.json()
                self._raise_for_cloudflare(payload)
                names = [z.get('name') for z in payload.get('result', [])][:5]
                note = f"Token verified — it can see {len(payload.get('result', []))} zone(s)" + (f' including: {", ".join(n for n in names if n)}' if names else '')
                return True, note
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f'Could not reach Cloudflare: {str(error)[:200]}')

    async def _zone(self, client: httpx.AsyncClient, config: dict) -> str:
        zone_id = (config or {}).get('zone_id', '')
        if zone_id:
            return zone_id
        zone_name = (config or {}).get('zone_name', '')
        if zone_name:
            r = await client.get('/zones', params={'name': zone_name})
            payload = self._raise_for_cloudflare(r.json())
            if payload.get('result'):
                return payload['result'][0]['id']
            raise ProviderError(f'No zone named "{zone_name}" is visible to this token')
        raise ProviderError('Set the zone_id (or zone_name) in the integration settings first')

    async def action(self, credentials: dict, config: dict, action: str, params: dict) -> dict:
        params = params or {}
        if action == 'purge_cache':
            try:
                async with await self._client(credentials) as client:
                    zone = await self._zone(client, config)
                    if params.get('urls'):
                        body = {'files': [str(u)[:300] for u in params.get('urls')[:30]]}
                    else:
                        body = {'purge_everything': True}
                    r = await client.post(f'/zones/{zone}/purge_cache', json=body)
                    payload = self._raise_for_cloudflare(r.json())
                    return {'ok': True, 'message': 'Cache purged' if body.get('purge_everything') else f"Purged {len(body.get('files', []))} URL(s)"}
            except ProviderError:
                raise
            except Exception as error:
                raise ProviderError(f'Purge failed: {str(error)[:200]}')
        if action == 'dev_mode':
            enable = str(params.get('enable', 'on')).lower() in ('on', 'true', '1', 'yes')
            try:
                async with await self._client(credentials) as client:
                    zone = await self._zone(client, config)
                    r = await client.patch(f'/zones/{zone}/settings/development_mode', json={'value': 'on' if enable else 'off'})
                    payload = self._raise_for_cloudflare(r.json())
                    return {'ok': True, 'message': f"Development mode {'enabled' if enable else 'disabled'}"}
            except ProviderError:
                raise
            except Exception as error:
                raise ProviderError(f'Dev-mode toggle failed: {str(error)[:200]}')
        raise ProviderError(f'Unknown action "{action}"')
