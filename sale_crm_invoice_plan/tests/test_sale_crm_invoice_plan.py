# Copyright 2026 KMEE
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import Command
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import TestSaleCommon


@tagged("post_install", "-at_install")
class TestSaleCrmInvoicePlan(TestSaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.owner_b = Partner.create({"name": "Owner B"})
        cls.owner_c = Partner.create({"name": "Owner C"})
        cls.template = cls.env["sale.invoice.plan.template"].create(
            {
                "name": "Half and half",
                "line_ids": [
                    Command.create({"percent": 50.0}),
                    Command.create({"partner_id": cls.owner_b.id, "percent": 50.0}),
                ],
            }
        )
        cls.customer = Partner.create(
            {"name": "Owner A", "invoice_plan_template_id": cls.template.id}
        )

    def test_lead_loads_template(self):
        with Form(
            self.env["crm.lead"].with_context(default_type="opportunity")
        ) as lead:
            lead.name = "Annual inspection"
            lead.partner_id = self.customer
        lead = lead.save()
        self.assertEqual(
            lead.invoice_plan_line_ids.mapped("payer_partner_id"),
            self.customer | self.owner_b,
        )

    def test_quotation_takes_lead_payers(self):
        lead = self.env["crm.lead"].create(
            {
                "name": "Annual inspection",
                "type": "opportunity",
                "partner_id": self.customer.id,
                "invoice_plan_line_ids": [
                    Command.create(
                        {"payer_partner_id": self.customer.id, "percent": 60.0}
                    ),
                    Command.create(
                        {"payer_partner_id": self.owner_c.id, "percent": 40.0}
                    ),
                ],
            }
        )
        context = lead.action_new_quotation()["context"]
        with Form(self.env["sale.order"].with_context(**context)) as order:
            self.assertEqual(len(order.invoice_plan_ids), 2)
        order = order.save()
        self.assertEqual(order.invoice_plan_mode, "payer")
        self.assertEqual(
            order.invoice_plan_ids.mapped("payer_partner_id"),
            self.customer | self.owner_c,
        )
        self.assertEqual(order.invoice_plan_ids.mapped("percent"), [60.0, 40.0])
