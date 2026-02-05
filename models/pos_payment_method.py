# -*- coding: utf-8 -*-
import json
import logging
import requests
from datetime import datetime, timedelta

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError, AccessDenied

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [('clover', 'Clover')]

    # Clover Configuration Fields
    clover_merchant_id = fields.Char(
        string='Merchant ID',
        help='Your Clover Merchant ID',
        copy=False,
        groups='base.group_erp_manager'
    )
    clover_device_id = fields.Char(
        string='Clover Serial Number',
        help='Device serial number (e.g., C031UQ12345678)',
        copy=False
    )
    clover_app_id = fields.Char(
        string='App ID',
        help='Clover App ID from developer dashboard',
        copy=False,
        groups='base.group_erp_manager'
    )
    clover_app_secret = fields.Char(
        string='App Secret',
        help='Clover App Secret from developer dashboard',
        copy=False,
        groups='base.group_erp_manager'
    )
    clover_access_token = fields.Text(
        string='Access Token',
        help='OAuth Access Token for Clover API',
        copy=False,
        groups='base.group_erp_manager'
    )
    clover_refresh_token = fields.Char(
        string='Refresh Token',
        copy=False,
        groups='base.group_erp_manager'
    )
    clover_token_expiry = fields.Datetime(
        string='Token Expiry',
        copy=False,
        groups='base.group_erp_manager'
    )
    clover_authorization_code = fields.Char(
        string='Authorization Code',
        help='OAuth authorization code received from Clover',
        copy=False,
        groups='base.group_erp_manager'
    )

    # Environment Settings
    clover_environment = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ], string='State', default='sandbox', required=True)

    clover_server = fields.Char(
        string='Server',
        compute='_compute_clover_server',
        store=True,
        readonly=True
    )

    clover_authorization_url = fields.Char(
        string='Authorization URL',
        compute='_compute_clover_authorization_url',
        readonly=True
    )

    clover_redirect_url = fields.Char(
        string='Redirect URL',
        compute='_compute_clover_redirect_url',
        readonly=True,
        help='Configure this URL in your Clover App settings as the OAuth redirect URI'
    )

    # Response buffer for async notifications
    clover_latest_response = fields.Text(
        copy=False,
        groups='base.group_erp_manager'
    )

    @api.depends('clover_environment')
    def _compute_clover_server(self):
        for record in self:
            if record.clover_environment == 'sandbox':
                record.clover_server = 'https://sandbox.dev.clover.com'
            else:
                record.clover_server = 'https://api.clover.com'

    @api.depends('clover_app_id', 'clover_merchant_id', 'clover_environment')
    def _compute_clover_authorization_url(self):
        for record in self:
            if record.clover_app_id and record.clover_merchant_id:
                base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                redirect_uri = f"{base_url}/payment/pos_clover/authorize"
                if record.clover_environment == 'sandbox':
                    auth_base = 'https://sandbox.dev.clover.com'
                else:
                    auth_base = 'https://www.clover.com'
                record.clover_authorization_url = (
                    f"{auth_base}/oauth/authorize?"
                    f"client_id={record.clover_app_id}&"
                    f"merchant_id={record.clover_merchant_id}&"
                    f"redirect_uri={redirect_uri}&"
                    f"response_type=code"
                )
            else:
                record.clover_authorization_url = False

    @api.depends('clover_environment')
    def _compute_clover_redirect_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            record.clover_redirect_url = f"{base_url}/payment/pos_clover/authorize"

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ['clover_device_id', 'clover_merchant_id']
        return params

    @api.constrains('clover_device_id')
    def _check_clover_device_id(self):
        for payment_method in self:
            if not payment_method.clover_device_id:
                continue
            existing = self.sudo().search([
                ('id', '!=', payment_method.id),
                ('clover_device_id', '=', payment_method.clover_device_id)
            ], limit=1)
            if existing:
                raise ValidationError(_(
                    'Device %(device)s is already used on payment method %(pm)s.',
                    device=payment_method.clover_device_id,
                    pm=existing.display_name
                ))

    def _is_write_forbidden(self, fields):
        return super()._is_write_forbidden(fields - {'clover_latest_response'})

    def _get_clover_api_base_url(self):
        """Get the base URL for Clover API calls"""
        self.ensure_one()
        if self.clover_environment == 'sandbox':
            return 'https://sandbox.dev.clover.com'
        return 'https://api.clover.com'

    def _get_clover_headers(self):
        """Get headers for Clover API requests"""
        self.ensure_one()
        return {
            'Authorization': f'Bearer {self.sudo().clover_access_token}',
            'Content-Type': 'application/json',
        }

    def action_generate_access_token(self):
        """Exchange authorization code for access token"""
        self.ensure_one()
        if not self.clover_authorization_code:
            raise UserError(_('Please enter the Authorization Code first.'))
        if not self.clover_app_id or not self.clover_app_secret:
            raise UserError(_('Please configure App ID and App Secret first.'))

        base_url = self._get_clover_api_base_url()
        token_url = f"{base_url}/oauth/token"

        try:
            response = requests.post(token_url, params={
                'client_id': self.clover_app_id,
                'client_secret': self.clover_app_secret,
                'code': self.clover_authorization_code,
            }, timeout=30)

            if response.status_code == 200:
                data = response.json()
                self.sudo().write({
                    'clover_access_token': data.get('access_token'),
                    'clover_token_expiry': datetime.now() + timedelta(days=365),
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Access token generated successfully!'),
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_(
                    'Failed to generate access token. Response: %s',
                    response.text
                ))
        except requests.exceptions.RequestException as e:
            raise UserError(_('Connection error: %s', str(e)))

    def action_fetch_clover_device(self):
        """Fetch device information from Clover"""
        self.ensure_one()
        if not self.clover_access_token:
            raise UserError(_('Please generate an access token first.'))
        if not self.clover_merchant_id:
            raise UserError(_('Please enter Merchant ID first.'))

        base_url = self._get_clover_api_base_url()
        devices_url = f"{base_url}/v3/merchants/{self.clover_merchant_id}/devices"

        try:
            response = requests.get(
                devices_url,
                headers=self._get_clover_headers(),
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                devices = data.get('elements', [])
                if devices:
                    # Get the first active device
                    device = devices[0]
                    self.clover_device_id = device.get('serial')
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Success'),
                            'message': _('Found device: %s', device.get('serial')),
                            'type': 'success',
                        }
                    }
                else:
                    raise UserError(_('No devices found for this merchant.'))
            else:
                raise UserError(_('Failed to fetch devices: %s', response.text))
        except requests.exceptions.RequestException as e:
            raise UserError(_('Connection error: %s', str(e)))

    def action_revoke_token(self):
        """Clear the access token"""
        self.ensure_one()
        self.sudo().write({
            'clover_access_token': False,
            'clover_refresh_token': False,
            'clover_token_expiry': False,
            'clover_authorization_code': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Access token revoked.'),
                'type': 'warning',
            }
        }

    def action_test_connection(self):
        """Test connection to Clover device"""
        self.ensure_one()
        if not self.clover_access_token:
            raise UserError(_('Please generate an access token first.'))
        if not self.clover_device_id:
            raise UserError(_('Please configure device serial number.'))

        try:
            result = self._clover_display_message(_('Connection test from Odoo POS'))
            if result:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Connection successful! Check your Clover device.'),
                        'type': 'success',
                    }
                }
        except Exception as e:
            raise UserError(_('Connection test failed: %s', str(e)))

    def _clover_display_message(self, message):
        """Display a message on the Clover terminal"""
        self.ensure_one()
        base_url = self._get_clover_api_base_url()
        endpoint = f"{base_url}/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/display_message"

        response = requests.post(
            endpoint,
            headers=self._get_clover_headers(),
            json={'message': message},
            timeout=30
        )
        return response.status_code == 200

    def _clover_show_welcome(self):
        """Display welcome screen on terminal"""
        self.ensure_one()
        base_url = self._get_clover_api_base_url()
        endpoint = f"{base_url}/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/welcome"

        self._log_clover_request('welcome', endpoint, {})
        response = requests.post(
            endpoint,
            headers=self._get_clover_headers(),
            timeout=30
        )
        self._log_clover_response('welcome', response)
        return response.status_code == 200

    def _clover_show_thank_you(self):
        """Display thank you screen on terminal"""
        self.ensure_one()
        base_url = self._get_clover_api_base_url()
        endpoint = f"{base_url}/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/thank_you"

        self._log_clover_request('thank_you', endpoint, {})
        response = requests.post(
            endpoint,
            headers=self._get_clover_headers(),
            timeout=30
        )
        self._log_clover_response('thank_you', response)
        return response.status_code == 200

    def proxy_clover_request(self, data, operation='sale'):
        """Proxy Clover API requests from the POS frontend"""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessDenied()

        if not self.clover_access_token:
            raise UserError(_('Clover access token not configured.'))

        base_url = self._get_clover_api_base_url()

        # Clear previous response for new payment requests
        if operation == 'sale':
            self.sudo().clover_latest_response = ''

        endpoint_map = {
            'sale': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/sale",
            'refund': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/refund",
            'void': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/void",
            'cancel': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/cancel",
            'status': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}",
            'welcome': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/welcome",
            'thank_you': f"/v3/merchants/{self.clover_merchant_id}/devices/{self.clover_device_id}/thank_you",
        }

        endpoint = endpoint_map.get(operation)
        if not endpoint:
            raise UserError(_('Unknown operation: %s', operation))

        url = f"{base_url}{endpoint}"

        try:
            self._log_clover_request(operation, url, data)

            if operation in ('status',):
                response = requests.get(
                    url,
                    headers=self._get_clover_headers(),
                    timeout=30
                )
            else:
                response = requests.post(
                    url,
                    headers=self._get_clover_headers(),
                    json=data,
                    timeout=120  # Longer timeout for payment operations
                )

            self._log_clover_response(operation, response)

            if response.status_code == 401:
                return {
                    'error': {
                        'status_code': response.status_code,
                        'message': 'Authentication failed. Please check your Clover credentials.'
                    }
                }

            if response.text:
                return response.json()
            return {'success': True}

        except requests.exceptions.Timeout:
            _logger.warning('Clover API request timeout for operation: %s', operation)
            return {
                'error': {
                    'status_code': 408,
                    'message': 'Request timeout. Please try again.'
                }
            }
        except requests.exceptions.RequestException as e:
            _logger.error('Clover API request error: %s', str(e))
            return {
                'error': {
                    'status_code': 500,
                    'message': str(e)
                }
            }

    def get_latest_clover_status(self):
        """Get the latest buffered response from Clover"""
        self.ensure_one()
        if not self.env.su and not self.env.user.has_group('point_of_sale.group_pos_user'):
            raise AccessDenied()

        latest_response = self.sudo().clover_latest_response
        return json.loads(latest_response) if latest_response else False

    def _log_clover_request(self, operation, url, data):
        """Log Clover API request"""
        _logger.info(
            'Clover API Request [%s] to %s: %s',
            operation, url, json.dumps(data) if data else 'No data'
        )
        # Create transaction log
        self.env['pos.clover.transaction.log'].sudo().create({
            'name': f'API-{operation}-{fields.Datetime.now()}',
            'payment_method_id': self.id,
            'transaction_type': operation,
            'request_data': json.dumps(data) if data else '',
            'request_timestamp': fields.Datetime.now(),
            'status': 'pending',
        })

    def _log_clover_response(self, operation, response):
        """Log Clover API response"""
        _logger.info(
            'Clover API Response [%s]: Status=%s, Body=%s',
            operation, response.status_code, response.text[:500] if response.text else 'Empty'
        )
        # Update the latest transaction log
        log = self.env['pos.clover.transaction.log'].sudo().search([
            ('payment_method_id', '=', self.id),
            ('transaction_type', '=', operation),
            ('status', '=', 'pending'),
        ], order='create_date desc', limit=1)

        if log:
            status = 'success' if response.status_code == 200 else 'failed'
            log.write({
                'response_data': response.text[:10000] if response.text else '',
                'response_timestamp': fields.Datetime.now(),
                'status': status,
                'error_message': response.text if response.status_code != 200 else '',
            })
