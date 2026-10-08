'''Simulated courier. Books a fake consignment and reports scripted tracking
states so shipment flows can be exercised without a real courier account.
'''
from providers.base import CourierProvider, register_courier, field


@register_courier
class MockCourier(CourierProvider):
    id = 'mock'
    label = 'Test courier (simulated)'
    supports_webhook = True
    docs_url = ''
    config_fields = []
    settings_fields = [field('scenario', 'Tracking scenario', required=False, placeholder='auto', help="'auto' advances on each track call, or a fixed status")]

    async def validate_config(self, credentials, sandbox):
        return True, 'Test courier is ready. Bookings are simulated.'

    async def create_shipment(self, order, config, credentials, parcel):
        from core import uid
        consignment = 'MOCK-' + uid()[:8].upper()
        return {'consignment_id': consignment, 'status': 'picked_up', 'tracking_url': ''}

    async def track(self, config, credentials, consignment_id):
        from core import stamp
        scenario = (config or {}).get('scenario', 'auto')
        fixed = ['picked_up', 'in_transit', 'delivered']
        if scenario in fixed:
            status = scenario
        else:
            count = sum(1 for ch in consignment_id) % len(fixed)
            status = fixed[count]
        return {'status': status, 'history': [{'status': status, 'at': stamp(), 'note': 'Simulated tracking event'}]}

    async def cancel_shipment(self, config, credentials, consignment_id):
        return {'ok': True, 'note': 'Simulated cancellation'}
