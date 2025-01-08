# -*- coding: utf-8 -*-

import logging
from odoo import models, fields
from odoo import fields, models, api, _
from odoo.osv import expression
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, safe_eval
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    case_num = fields.Integer('Case Number')
    lawyer_id = fields.Many2one('res.partner', 'Lawyer')
    lawyer_code = fields.Char(related='lawyer_id.lawyer_code',string='Lawyer Code')
    customer_id = fields.Many2one('res.partner', 'Customer')
    customer_code = fields.Char(related='customer_id.customer_code',string='Customer Code')

    expense_name = fields.Char(related='account_id.name',string='Expense Name')

    black_num = fields.Char('Black Numbers')
    red_num = fields.Char('Red Numbers')
    finco = fields.Selection([('stamc','STAMC')])
    department = fields.Integer('Department')
    agency = fields.Selection([('stamc','STAMC')])
    entity_num = fields.Integer('Entity Number')
    working_date = fields.Date('Working Date')
    court_date = fields.Date('Court Date')

class AccountAccount(models.Model):
    _inherit = 'account.account'

    @api.depends('code')
    def _compute_display_name(self):
        vals = super()._compute_display_name()
        for data in self:
            data.display_name = data.code
        return vals













