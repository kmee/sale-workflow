# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import Command, api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    invoice_plan_line_ids = fields.One2many(
        comodel_name="crm.lead.invoice.plan",
        inverse_name="lead_id",
        string="Payers",
        copy=True,
        help="Payers of the invoicing, copied to the new quotations.",
    )
    invoice_plan_total_percent = fields.Float(
        compute="_compute_invoice_plan_total_percent",
        digits="Sales Invoice Plan Percent",
    )

    @api.depends("invoice_plan_line_ids.percent")
    def _compute_invoice_plan_total_percent(self):
        for lead in self:
            lead.invoice_plan_total_percent = sum(
                lead.invoice_plan_line_ids.mapped("percent")
            )

    @api.onchange("partner_id")
    def _onchange_partner_id_invoice_plan(self):
        template = self.partner_id.commercial_partner_id.invoice_plan_template_id
        if not template or self.invoice_plan_line_ids:
            return
        self.invoice_plan_line_ids = [
            Command.create(
                {
                    "sequence": line.sequence,
                    "payer_partner_id": (
                        line.partner_id or self.partner_id.commercial_partner_id
                    ).id,
                    "percent": line.percent,
                }
            )
            for line in template.line_ids
        ]


class CrmLeadInvoicePlan(models.Model):
    _name = "crm.lead.invoice.plan"
    _description = "Opportunity Payer"
    _order = "sequence, id"

    lead_id = fields.Many2one(
        comodel_name="crm.lead",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    payer_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Payer",
        required=True,
    )
    percent = fields.Float(
        digits="Sales Invoice Plan Percent",
        required=True,
    )
