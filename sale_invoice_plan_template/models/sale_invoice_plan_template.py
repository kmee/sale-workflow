# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class SaleInvoicePlanTemplate(models.Model):
    _name = "sale.invoice.plan.template"
    _description = "Invoice Plan Template by Payer"
    _order = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    line_ids = fields.One2many(
        comodel_name="sale.invoice.plan.template.line",
        inverse_name="template_id",
        string="Payers",
        copy=True,
    )
    total_percent = fields.Float(
        compute="_compute_total_percent",
        digits="Sales Invoice Plan Percent",
    )

    @api.depends("line_ids.percent")
    def _compute_total_percent(self):
        for template in self:
            template.total_percent = sum(template.line_ids.mapped("percent"))

    @api.constrains("line_ids")
    def _check_lines(self):
        prec = self.env["decimal.precision"].precision_get("Sales Invoice Plan Percent")
        for template in self:
            if float_compare(template.total_percent, 100.0, precision_digits=prec):
                raise ValidationError(
                    self.env._(
                        "The payers of the template %(name)s must add up to 100%%."
                    )
                    % {"name": template.name}
                )
            payers = template.line_ids.mapped(lambda line: line.partner_id.id)
            if len(set(payers)) < len(payers):
                raise ValidationError(
                    self.env._("Each payer can appear only once in the template.")
                )

    def _prepare_invoice_plan_vals(self, order):
        """Invoice plan lines of the order. A line without partner is the
        invoice address of the order."""
        self.ensure_one()
        return [
            {
                "payer_partner_id": (line.partner_id or order.partner_invoice_id).id,
                "percent": line.percent,
            }
            for line in self.line_ids
        ]


class SaleInvoicePlanTemplateLine(models.Model):
    _name = "sale.invoice.plan.template.line"
    _description = "Invoice Plan Template Payer"
    _order = "sequence, id"

    template_id = fields.Many2one(
        comodel_name="sale.invoice.plan.template",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Payer",
        help="Leave empty for the invoice address of the order.",
    )
    percent = fields.Float(
        digits="Sales Invoice Plan Percent",
        required=True,
    )
