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

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_lawyer = fields.Boolean('Is Lawyer')
    is_customer = fields.Boolean('Is Customer')
    lawyer_code = fields.Char('Lawyer Code')
    customer_code = fields.Char('Customer Code')