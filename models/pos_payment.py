# -*- coding: utf-8 -*-
from odoo import fields, models, api


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    # Clover Transaction Fields
    clover_payment_id = fields.Char(
        string='Clover Payment ID',
        help='Payment ID from Clover',
        readonly=True,
        copy=False
    )
    clover_order_id = fields.Char(
        string='Clover Order ID',
        help='Order ID from Clover',
        readonly=True,
        copy=False
    )
    clover_external_payment_id = fields.Char(
        string='External Payment ID',
        readonly=True,
        copy=False
    )
    clover_refund_id = fields.Char(
        string='Refund ID',
        readonly=True,
        copy=False
    )
    clover_employee_id = fields.Char(
        string='Employee ID',
        readonly=True,
        copy=False
    )
    clover_result = fields.Char(
        string='Result',
        readonly=True,
        copy=False
    )
    clover_amount = fields.Float(
        string='Clover Amount',
        readonly=True,
        copy=False
    )
    clover_auth_code = fields.Char(
        string='Auth Code',
        readonly=True,
        copy=False
    )
    clover_card_type = fields.Char(
        string='Card Type',
        readonly=True,
        copy=False
    )
    clover_card_last_four = fields.Char(
        string='Last 4',
        readonly=True,
        copy=False
    )
    clover_reference = fields.Char(
        string='Reference',
        readonly=True,
        copy=False
    )
    clover_created_time = fields.Datetime(
        string='Created Time',
        readonly=True,
        copy=False
    )
    clover_type = fields.Char(
        string='Type',
        readonly=True,
        copy=False
    )

