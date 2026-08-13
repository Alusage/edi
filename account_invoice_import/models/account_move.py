# Copyright 2015-2021 Akretion France (https://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, api, fields, models
from odoo.tools import is_html_empty


class AccountMove(models.Model):
    _inherit = "account.move"

    import_warnings = fields.Html(readonly=True)
    show_import_warnings = fields.Boolean(compute="_compute_show_import_warnings")
    # 15.0: fields.Json only exists from 16.0 on. The payload is kept as a
    # JSON string, and every reader/writer goes through json.loads/dumps.
    import_partner_data = fields.Text()

    def _check_total_amount(self, amount_total):
        """15.0 stand-in for the account.move method added in 16.0.

        16.0 absorbs the rounding difference in the tax group of tax_totals;
        neither that method nor that field exist here (15.0 has tax_totals_json),
        so force the difference onto the first non-zero tax line, which is what
        the 14.0 version of this module did. Does nothing when the invoice
        carries no tax line — the caller reports that case to the chatter.
        """
        self.ensure_one()
        if not amount_total:
            return
        currency = self.currency_id
        diff = amount_total - self.amount_total
        if currency.is_zero(diff):
            return
        for mline in self.line_ids:
            if not mline.tax_line_id or currency.is_zero(mline.amount_currency):
                continue
            sign = 1 if currency.compare_amounts(mline.amount_currency, 0) >= 0 else -1
            new_amount_currency = currency.round(mline.amount_currency + sign * diff)
            new_balance = currency._convert(
                new_amount_currency,
                self.company_id.currency_id,
                self.company_id,
                self.date,
            )
            vals = {"amount_currency": new_amount_currency}
            if self.company_id.currency_id.compare_amounts(new_balance, 0) > 0:
                vals.update({"debit": new_balance, "credit": 0})
            else:
                vals.update({"debit": 0, "credit": -new_balance})
            mline.with_context(check_move_validity=False).write(vals)
            self.with_context(check_move_validity=False)._recompute_dynamic_lines()
            self._check_balanced()
            break

    @api.depends("state", "import_warnings")
    def _compute_show_import_warnings(self):
        for move in self:
            show = False
            if move.state == "draft" and not is_html_empty(move.import_warnings):
                show = True
            move.show_import_warnings = show

    def _invoice_import_set_partner_and_update_lines(self, partner):
        self.ensure_one()
        initial_fp = self.fiscal_position_id
        fp = partner.property_account_position_id
        self.write({"partner_id": partner.id})
        # Writing 'partner_id' triggers the update of payment terms, payment mode,
        # fiscal_position_id, etc... on the invoice because they are all computed
        # fields now
        if fp and not initial_fp:
            assert self.fiscal_position_id == fp
            account_map = {}  # key = source account, value = dest account
            tax_map = {}
            for acc_entry in fp.account_ids:
                if acc_entry.account_src_id and acc_entry.account_dest_id:
                    account_map[
                        acc_entry.account_src_id.id
                    ] = acc_entry.account_dest_id.id
            for tax_entry in fp.tax_ids:
                tax_map[tax_entry.tax_src_id.id] = tax_entry.tax_dest_id.id or False
            for iline in self.invoice_line_ids.filtered(
                lambda x: not x.display_type
            ):
                vals = {}
                if iline.account_id.id in account_map:
                    vals["account_id"] = account_map[iline.account_id.id]
                if iline.tax_ids:
                    new_tax_ids = []
                    for tax in iline.tax_ids:
                        new_tax_id = tax_map.get(tax.id, tax.id)
                        if new_tax_id:
                            new_tax_ids.append(new_tax_id)
                    if new_tax_ids != iline.tax_ids.ids:
                        vals["tax_ids"] = [Command.set(new_tax_ids)]
                if vals:
                    iline.write(vals)
