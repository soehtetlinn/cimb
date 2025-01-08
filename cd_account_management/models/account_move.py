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
    lawyer_code = fields.Integer(related='lawyer_id.lawyer_code',string='Lawyer Code')
    customer_id = fields.Many2one('res.partner', 'Customer')
    customer_code = fields.Integer(related='customer_id.customer_code',string='Customer Code')
    expense_category = fields.Char('Expense Category')
    withdrawal_details = fields.Char('Withdrawal Details')
    black_num = fields.Char('Black Numbers')
    red_num = fields.Char('Red Numbers')
    finco = fields.Selection([('stamc','STAMC')])
    cost_code = fields.Integer('Expense Code')
    budget_expense_code = fields.Integer('Budget Expense Code')
    department = fields.Integer('Department')
    agency = fields.Selection([('stamc','STAMC')])
    entity_num = fields.Integer('Entity Number')
    working_date = fields.Date('Working Date')
    court_date = fields.Date('Court Date')












