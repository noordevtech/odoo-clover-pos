# -*- coding: utf-8 -*-
from odoo import fields, models, api


class PosCloverTransactionLog(models.Model):
    _name = 'pos.clover.transaction.log'
    _description = 'Clover Transaction Log'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Reference',
        required=True,
        index=True
    )
    payment_method_id = fields.Many2one(
        'pos.payment.method',
        string='Payment Method',
        ondelete='cascade',
        index=True
    )
    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        ondelete='set null',
        index=True
    )
    pos_payment_id = fields.Many2one(
        'pos.payment',
        string='POS Payment',
        ondelete='set null'
    )

    # Transaction Details
    transaction_type = fields.Selection([
        ('sale', 'Sale'),
        ('auth', 'Authorization'),
        ('capture', 'Capture'),
        ('refund', 'Refund'),
        ('void', 'Void'),
        ('cancel', 'Cancel'),
        ('status', 'Status Check'),
        ('welcome', 'Welcome Screen'),
        ('thank_you', 'Thank You Screen'),
    ], string='Type', required=True, index=True)

    amount = fields.Float(string='Amount')
    currency = fields.Char(string='Currency', default='USD')

    # Clover Response Data
    clover_payment_id = fields.Char(string='Clover Payment ID')
    clover_order_id = fields.Char(string='Clover Order ID')
    card_last_four = fields.Char(string='Card Last 4 Digits')
    card_type = fields.Char(string='Card Type')
    auth_code = fields.Char(string='Authorization Code')

    # Status & Response
    status = fields.Selection([
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('timeout', 'Timeout'),
    ], string='Status', default='pending', required=True, index=True)

    error_message = fields.Text(string='Error Message')

    # API Log
    request_data = fields.Text(string='API Request')
    response_data = fields.Text(string='API Response')
    request_timestamp = fields.Datetime(string='Request Time')
    response_timestamp = fields.Datetime(string='Response Time')

    # Computed fields
    duration = fields.Float(
        string='Duration (s)',
        compute='_compute_duration',
        store=True
    )

    @api.depends('request_timestamp', 'response_timestamp')
    def _compute_duration(self):
        for record in self:
            if record.request_timestamp and record.response_timestamp:
                delta = record.response_timestamp - record.request_timestamp
                record.duration = delta.total_seconds()
            else:
                record.duration = 0

    def action_view_request(self):
        """Open a popup to view the full request data"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Request Data',
            'res_model': 'pos.clover.transaction.log',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
