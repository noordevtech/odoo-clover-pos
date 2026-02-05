# -*- coding: utf-8 -*-
{
    'name': 'POS Clover Connector',
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'sequence': 6,
    'summary': 'Integrate Odoo POS with Clover Payment Terminals',
    'description': """
        Clover Terminal Integration with Odoo POS
        ==========================================
        
        Features:
        - Process card payments via Clover terminal
        - Real-time transaction synchronization
        - Multi-terminal support
        - Refunds and reversals
        - Comprehensive transaction logging
        - Error handling with retry mechanisms
        - OAuth 2.0 authentication flow
    """,
    'author': 'Your Company',
    'website': 'https://yourwebsite.com',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_payment_method_views.xml',
        'views/clover_transaction_log_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'Clover_pos/static/src/app/**/*',
        ],
        'web.assets_backend': [
            'Clover_pos/static/src/backend/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
