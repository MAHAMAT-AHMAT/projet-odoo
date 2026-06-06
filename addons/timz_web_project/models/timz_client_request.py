from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TimzClientRequest(models.Model):
    _name = 'timz.client.request'
    _description = 'Demande Client — Timz & Co'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    # ─── Identification ───────────────────────────────────────────────────────
    name = fields.Char(
        string='Référence',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('Nouveau'),
        tracking=True,
    )
    client_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        tracking=True,
        index=True,
    )
    email = fields.Char(
        related='client_id.email',
        string='Email',
        readonly=True,
    )
    phone = fields.Char(
        related='client_id.phone',
        string='Téléphone',
        readonly=True,
    )

    # ─── Détail de la demande ──────────────────────────────────────────────────
    description = fields.Text(
        string='Description du besoin',
        required=True,
    )
    project_type = fields.Selection([
        ('website', 'Site Web Vitrine'),
        ('ecommerce', 'Site E-Commerce'),
        ('webapp', 'Application Web'),
        ('api', 'API / Web Service'),
        ('maintenance', 'Maintenance / Évolution'),
    ], string='Type de projet', required=True, tracking=True)
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Haute'),
        ('2', 'Urgente'),
    ], string='Priorité', default='0')
    budget = fields.Monetary(
        string='Budget estimé (€)',
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id,
    )
    deadline = fields.Date(
        string='Date souhaitée de livraison',
        tracking=True,
    )
    note = fields.Text(string='Notes internes')

    # ─── Workflow ─────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('new', 'Nouvelle'),
        ('qualified', 'Qualifiée'),
        ('proposal', 'Proposition envoyée'),
        ('won', 'Gagnée'),
        ('lost', 'Perdue'),
    ], string='État', default='new', tracking=True,
       group_expand='_expand_states', index=True)

    user_id = fields.Many2one(
        'res.users',
        string='Responsable commercial',
        default=lambda self: self.env.user,
        tracking=True,
    )

    # ─── Relations vers modules standards ────────────────────────────────────
    crm_lead_id = fields.Many2one(
        'crm.lead',
        string='Opportunité CRM',
        readonly=True,
        copy=False,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Devis / Commande',
        readonly=True,
        copy=False,
    )
    web_project_id = fields.Many2one(
        'timz.web.project',
        string='Projet Web',
        readonly=True,
        copy=False,
    )

    # ─── Computed ─────────────────────────────────────────────────────────────
    sale_order_count = fields.Integer(
        string='Nb. Devis',
        compute='_compute_sale_order_count',
    )
    kanban_state = fields.Selection([
        ('normal', 'En cours'),
        ('done', 'Prêt'),
        ('blocked', 'Bloqué'),
    ], string='État Kanban', default='normal', tracking=True)

    # ─── Séquence ─────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('Nouveau')) == _('Nouveau'):
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('timz.client.request')
                    or _('Nouveau')
                )
        return super().create(vals_list)

    # ─── Computed methods ──────────────────────────────────────────────────────
    def _compute_sale_order_count(self):
        for rec in self:
            rec.sale_order_count = 1 if rec.sale_order_id else 0

    @api.model
    def _expand_states(self, states, domain, order):
        return [key for key, _val in self._fields['state'].selection]

    # ─── Actions de workflow ──────────────────────────────────────────────────
    def action_qualify(self):
        for rec in self:
            if rec.state != 'new':
                raise UserError(_("Seules les demandes nouvelles peuvent être qualifiées."))
            rec.state = 'qualified'
            lead = self.env['crm.lead'].create({
                'name': f"[Timz] {rec.name} – {rec.client_id.name}",
                'partner_id': rec.client_id.id,
                'description': rec.description,
                'expected_revenue': rec.budget,
                'user_id': rec.user_id.id,
                'type': 'opportunity',
            })
            rec.crm_lead_id = lead.id
            rec.message_post(
                body=_("Demande qualifiée. Opportunité CRM %s créée.") % lead.name
            )

    def action_send_proposal(self):
        for rec in self:
            if rec.state != 'qualified':
                raise UserError(_(
                    "La demande doit être qualifiée avant d'envoyer une proposition."
                ))
            rec.state = 'proposal'
            # Correspondance type de projet → produit de service Timz
            type_to_product_ref = {
                'website': 'timz_web_project.product_timz_site_vitrine',
                'ecommerce': 'timz_web_project.product_timz_ecommerce',
                'webapp': 'timz_web_project.product_timz_webapp',
                'mobile': 'timz_web_project.product_timz_mobile',
                'erp': 'timz_web_project.product_timz_erp',
            }
            product_ref = type_to_product_ref.get(rec.project_type)
            product = None
            if product_ref:
                tmpl = self.env.ref(product_ref, raise_if_not_found=False)
                if tmpl:
                    product = tmpl.product_variant_id
            # Fallback : n'importe quel produit service
            if not product:
                product = self.env['product.product'].search(
                    [('type', '=', 'service')], limit=1
                )
            order_vals = {
                'partner_id': rec.client_id.id,
                'note': rec.description,
                'user_id': rec.user_id.id,
            }
            if product:
                order_vals['order_line'] = [(0, 0, {
                    'product_id': product.id,
                    'name': rec.description or product.name,
                    'product_uom_qty': 1.0,
                    'price_unit': rec.budget,
                })]
            sale_order = self.env['sale.order'].create(order_vals)
            rec.sale_order_id = sale_order.id
            rec.message_post(
                body=_("Proposition envoyée. Devis %s créé (montant : %s €).") % (sale_order.name, rec.budget)
            )

    def action_mark_won(self):
        for rec in self:
            if rec.state != 'proposal':
                raise UserError(_(
                    "Une proposition doit être envoyée avant de marquer la demande comme gagnée."
                ))
            rec.state = 'won'
            if rec.crm_lead_id:
                rec.crm_lead_id.action_set_won()
            rec.message_post(body=_("Demande marquée comme gagnée."))

    def action_mark_lost(self):
        for rec in self:
            if rec.state in ('won', 'lost'):
                raise UserError(_("Cette demande ne peut plus être perdue."))
            rec.state = 'lost'
            if rec.crm_lead_id:
                rec.crm_lead_id.action_set_lost()
            rec.message_post(body=_("Demande marquée comme perdue."))

    def action_create_project(self):
        self.ensure_one()
        if self.state != 'won':
            raise UserError(_("La demande doit être gagnée pour créer un projet."))
        if self.web_project_id:
            raise UserError(_("Un projet web existe déjà pour cette demande."))
        project = self.env['timz.web.project'].create({
            'name': f"Projet – {self.client_id.name} ({self.get_project_type_label()})",
            'client_request_id': self.id,
            'client_id': self.client_id.id,
            'sale_order_id': self.sale_order_id.id if self.sale_order_id else False,
            'project_type': self.project_type,
            'budget': self.budget,
            'deadline': self.deadline,
        })
        self.web_project_id = project.id
        self.message_post(
            body=_("Projet web %s créé depuis cette demande.") % project.name
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'timz.web.project',
            'res_id': project.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_project_type_label(self):
        self.ensure_one()
        types = dict(self._fields['project_type'].selection)
        return types.get(self.project_type, self.project_type)

    # ─── Smart buttons ────────────────────────────────────────────────────────
    def action_view_crm_lead(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': self.crm_lead_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_web_project(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'timz.web.project',
            'res_id': self.web_project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ─── Contraintes ──────────────────────────────────────────────────────────
    @api.constrains('budget')
    def _check_budget(self):
        for rec in self:
            if rec.budget and rec.budget < 0:
                raise ValidationError(_("Le budget ne peut pas être négatif."))
