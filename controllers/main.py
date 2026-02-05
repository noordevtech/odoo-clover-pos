# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosCloverController(http.Controller):

    @http.route('/payment/pos_clover/authorize', type='http', auth='user', website=True)
    def clover_oauth_callback(self, code=None, merchant_id=None, client_id=None, **kwargs):
        """
        Handle OAuth callback from Clover authorization.
        User is redirected here after authorizing the app in Clover.
        """
        _logger.info('Clover OAuth callback received: code=%s, merchant_id=%s', code, merchant_id)

        if not code:
            return request.render('Clover_pos.oauth_error', {
                'error': 'No authorization code received from Clover.'
            })

        # Find the payment method by merchant_id or client_id
        domain = []
        if merchant_id:
            domain.append(('clover_merchant_id', '=', merchant_id))
        if client_id:
            domain.append(('clover_app_id', '=', client_id))

        if not domain:
            return request.render('Clover_pos.oauth_error', {
                'error': 'Could not identify the payment method. Please try again.'
            })

        payment_method = request.env['pos.payment.method'].sudo().search(domain, limit=1)

        if not payment_method:
            return request.render('Clover_pos.oauth_error', {
                'error': 'Payment method not found. Please configure Clover settings first.'
            })

        # Store the authorization code
        payment_method.write({
            'clover_authorization_code': code,
        })

        return request.render('Clover_pos.oauth_success', {
            'payment_method': payment_method,
            'code': code,
        })

    @http.route('/pos_clover/notification', type='json', methods=['POST'], auth='public', csrf=False, save_session=False)
    def clover_notification(self):
        """
        Handle async payment notifications from Clover.
        This is called by Clover webhooks when payment status changes.
        """
        try:
            data = json.loads(request.httprequest.data)
        except (json.JSONDecodeError, TypeError):
            _logger.warning('Invalid JSON in Clover notification')
            return {'status': 'error', 'message': 'Invalid JSON'}

        _logger.info('Clover notification received: %s', json.dumps(data)[:500])

        # Extract payment information
        payment_data = data.get('payment', {})
        device_id = data.get('deviceId') or payment_data.get('device', {}).get('id')
        merchant_id = data.get('merchantId')

        if not device_id and not merchant_id:
            _logger.warning('Clover notification missing device or merchant ID')
            return {'status': 'error', 'message': 'Missing identifiers'}

        # Find the payment method
        domain = [('use_payment_terminal', '=', 'clover')]
        if device_id:
            domain.append(('clover_device_id', '=', device_id))
        if merchant_id:
            domain.append(('clover_merchant_id', '=', merchant_id))

        payment_method = request.env['pos.payment.method'].sudo().search(domain, limit=1)

        if not payment_method:
            _logger.warning('No payment method found for Clover notification: device=%s, merchant=%s', device_id, merchant_id)
            return {'status': 'error', 'message': 'Payment method not found'}

        # Store the response for the POS to pick up
        payment_method.clover_latest_response = json.dumps(data)

        # Notify the POS via websocket
        self._notify_pos_session(payment_method, data)

        return {'status': 'ok'}

    def _notify_pos_session(self, payment_method, data):
        """Send notification to POS sessions using this payment method"""
        # Find active POS sessions using this payment method
        pos_configs = payment_method.config_ids
        for config in pos_configs:
            try:
                config._notify('CLOVER_LATEST_RESPONSE', config.id)
            except Exception as e:
                _logger.error('Failed to notify POS config %s: %s', config.id, str(e))

    @http.route('/pos_clover/test', type='http', auth='user')
    def test_endpoint(self, **kwargs):
        """Simple test endpoint to verify the controller is working"""
        return request.make_response(
            json.dumps({'status': 'ok', 'message': 'Clover POS controller is active'}),
            headers=[('Content-Type', 'application/json')]
        )
