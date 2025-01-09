# -*- coding: utf-8 -*-

import logging
from collections import defaultdict
from odoo import models, fields
from odoo import fields, models, api, _
from odoo.osv import expression
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF, safe_eval
from odoo.exceptions import UserError, ValidationError
from odoo.exceptions import UserError, ValidationError, AccessError, RedirectWarning
from odoo.tools import (
    create_index,
    date_utils,
    float_compare,
    float_is_zero,
    float_repr,
    format_amount,
    format_date,
    formatLang,
    frozendict,
    get_lang,
    groupby,
    index_exists,
    OrderedSet,
    SQL,
)

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        """Post/Validate the documents.

        Posting the documents will give it a number, and check that the document is
        complete (some fields might not be required if not posted but are required
        otherwise).
        If the journal is locked with a hash table, it will be impossible to change
        some fields afterwards.

        :param soft (bool): if True, future documents are not immediately posted,
            but are set to be auto posted automatically at the set accounting date.
            Nothing will be performed on those documents before the accounting date.
        :return Model<account.move>: the documents that have been posted
        """
        if not self.env.su and not self.env.user.has_group('account.group_account_invoice'):
            raise AccessError(_("You don't have the access rights to post an invoice."))

        # Avoid marking is_manually_modified as True when posting an invoice
        self = self.with_context(skip_is_manually_modified=True)  # noqa: PLW0642

        validation_msgs = set()

        for invoice in self.filtered(lambda move: move.is_invoice(include_receipts=True)):
            if (
                invoice.quick_edit_mode
                and invoice.quick_edit_total_amount
                and invoice.currency_id.compare_amounts(invoice.quick_edit_total_amount, invoice.amount_total) != 0
            ):
                validation_msgs.add(_(
                    "The current total is %(current_total)s but the expected total is %(expected_total)s. In order to post the invoice/bill, "
                    "you can adjust its lines or the expected Total (tax inc.).",
                    current_total=formatLang(self.env, invoice.amount_total, currency_obj=invoice.currency_id),
                    expected_total=formatLang(self.env, invoice.quick_edit_total_amount, currency_obj=invoice.currency_id),
                ))
            if invoice.partner_bank_id and not invoice.partner_bank_id.active:
                validation_msgs.add(_(
                    "The recipient bank account linked to this invoice is archived.\n"
                    "So you cannot confirm the invoice."
                ))
            if float_compare(invoice.amount_total, 0.0, precision_rounding=invoice.currency_id.rounding) < 0:
                validation_msgs.add(_(
                    "You cannot validate an invoice with a negative total amount. "
                    "You should create a credit note instead. "
                    "Use the action menu to transform it into a credit note or refund."
                ))

            # if not invoice.partner_id:
            #     if invoice.is_sale_document():
            #         validation_msgs.add(_("The field 'Customer' is required, please complete it to validate the Customer Invoice."))
            #     elif invoice.is_purchase_document():
            #         validation_msgs.add(_("The field 'Vendor' is required, please complete it to validate the Vendor Bill."))

            # Handle case when the invoice_date is not set. In that case, the invoice_date is set at today and then,
            # lines are recomputed accordingly.
            if not invoice.invoice_date:
                if invoice.is_sale_document(include_receipts=True):
                    invoice.invoice_date = fields.Date.context_today(self)
                # elif invoice.is_purchase_document(include_receipts=True):
                #     validation_msgs.add(_("The Bill/Refund date is required to validate this document."))

        for move in self:
            if move.state in ['posted', 'cancel']:
                validation_msgs.add(_('The entry %(name)s (id %(id)s) must be in draft.', name=move.name, id=move.id))
            if not move.line_ids.filtered(lambda line: line.display_type not in ('line_section', 'line_note')):
                validation_msgs.add(_('You need to add a line before posting.'))
            if not soft and move.auto_post != 'no' and move.date > fields.Date.context_today(self):
                date_msg = move.date.strftime(get_lang(self.env).date_format)
                validation_msgs.add(_("This move is configured to be auto-posted on %(date)s", date=date_msg))
            if not move.journal_id.active:
                validation_msgs.add(_(
                    "You cannot post an entry in an archived journal (%(journal)s)",
                    journal=move.journal_id.display_name,
                ))
            if move.display_inactive_currency_warning:
                validation_msgs.add(_(
                    "You cannot validate a document with an inactive currency: %s",
                    move.currency_id.name
                ))

            if move.line_ids.account_id.filtered(lambda account: account.deprecated) and not self._context.get('skip_account_deprecation_check'):
                validation_msgs.add(_("A line of this move is using a deprecated account, you cannot post it."))

            # If the field autocheck_on_post is set, we want the checked field on the move to be checked
            move.checked = move.journal_id.autocheck_on_post

        if validation_msgs:
            msg = "\n".join([line for line in validation_msgs])
            raise UserError(msg)

        if soft:
            future_moves = self.filtered(lambda move: move.date > fields.Date.context_today(self))
            for move in future_moves:
                if move.auto_post == 'no':
                    move.auto_post = 'at_date'
                msg = _('This move will be posted at the accounting date: %(date)s', date=format_date(self.env, move.date))
                move.message_post(body=msg)
            to_post = self - future_moves
        else:
            to_post = self

        for move in to_post:
            affects_tax_report = move._affect_tax_report()
            lock_dates = move._get_violated_lock_dates(move.date, affects_tax_report)
            if lock_dates:
                move.date = move._get_accounting_date(move.invoice_date or move.date, affects_tax_report, lock_dates=lock_dates)

        # Create the analytic lines in batch is faster as it leads to less cache invalidation.
        to_post.line_ids._create_analytic_lines()

        # Trigger copying for recurring invoices
        to_post.filtered(lambda m: m.auto_post not in ('no', 'at_date'))._copy_recurring_entries()

        for invoice in to_post:
            # Fix inconsistencies that may occure if the OCR has been editing the invoice at the same time of a user. We force the
            # partner on the lines to be the same as the one on the move, because that's the only one the user can see/edit.
            wrong_lines = invoice.is_invoice() and invoice.line_ids.filtered(lambda aml:
                aml.partner_id != invoice.commercial_partner_id
                and aml.display_type not in ('line_note', 'line_section')
            )
            if wrong_lines:
                wrong_lines.write({'partner_id': invoice.commercial_partner_id.id})

        # reconcile if state is in draft and move has reversal_entry_id set
        draft_reverse_moves = to_post.filtered(lambda move: move.reversed_entry_id and move.reversed_entry_id.state == 'posted')

        to_post.write({
            'state': 'posted',
            'posted_before': True,
        })

        draft_reverse_moves.reversed_entry_id._reconcile_reversed_moves(draft_reverse_moves, self._context.get('move_reverse_cancel', False))
        to_post.line_ids._reconcile_marked()

        for invoice in to_post:
            invoice.message_subscribe([
                p.id
                for p in [invoice.partner_id]
                if p not in invoice.sudo().message_partner_ids
            ])

        customer_count, supplier_count = defaultdict(int), defaultdict(int)
        for invoice in to_post:
            if invoice.is_sale_document():
                customer_count[invoice.partner_id] += 1
            elif invoice.is_purchase_document():
                supplier_count[invoice.partner_id] += 1
            elif invoice.move_type == 'entry':
                sale_amls = invoice.line_ids.filtered(lambda line: line.partner_id and line.account_id.account_type == 'asset_receivable')
                for partner in sale_amls.mapped('partner_id'):
                    customer_count[partner] += 1
                purchase_amls = invoice.line_ids.filtered(lambda line: line.partner_id and line.account_id.account_type == 'liability_payable')
                for partner in purchase_amls.mapped('partner_id'):
                    supplier_count[partner] += 1
        for partner, count in customer_count.items():
            (partner | partner.commercial_partner_id)._increase_rank('customer_rank', count)
        for partner, count in supplier_count.items():
            (partner | partner.commercial_partner_id)._increase_rank('supplier_rank', count)

        # Trigger action for paid invoices if amount is zero
        to_post.filtered(
            lambda m: m.is_invoice(include_receipts=True) and m.currency_id.is_zero(m.amount_total)
        )._invoice_paid_hook()

        return to_post

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













