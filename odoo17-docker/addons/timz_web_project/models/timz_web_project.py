from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TimzWebProject(models.Model):
    _name = 'timz.web.project'
    _description = 'Projet Web — Timz & Co'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    # ─── Identification ───────────────────────────────────────────────────────
    name = fields.Char(
        string='Nom du projet',
        required=True,
        tracking=True,
    )
    reference = fields.Char(
        string='Référence',
        copy=False,
        readonly=True,
        default=lambda self: _('Nouveau'),
        index=True,
    )
    color = fields.Integer(string='Couleur kanban')
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Haute'),
        ('2', 'Urgente'),
    ], string='Priorité', default='0')

    # ─── Client & demande ─────────────────────────────────────────────────────
    client_id = fields.Many2one(
        'res.partner',
        string='Client',
        required=True,
        tracking=True,
        index=True,
    )
    client_request_id = fields.Many2one(
        'timz.client.request',
        string='Demande client d\'origine',
        readonly=True,
        ondelete='set null',
    )

    # ─── Caractéristiques projet ──────────────────────────────────────────────
    project_type = fields.Selection([
        ('website', 'Site Web Vitrine'),
        ('ecommerce', 'Site E-Commerce'),
        ('webapp', 'Application Web'),
        ('api', 'API / Web Service'),
        ('maintenance', 'Maintenance / Évolution'),
    ], string='Type de projet', required=True, tracking=True)

    technology = fields.Selection([
        ('django', 'Django / Python'),
        ('laravel', 'Laravel / PHP'),
        ('react', 'React.js'),
        ('vue', 'Vue.js'),
        ('angular', 'Angular'),
        ('nodejs', 'Node.js'),
        ('wordpress', 'WordPress'),
        ('odoo', 'Odoo / Python'),
        ('other', 'Autre'),
    ], string='Technologie principale', tracking=True)

    description = fields.Html(string='Description du projet')
    deliverables = fields.Text(string='Livrables attendus')

    # ─── Dates ────────────────────────────────────────────────────────────────
    start_date = fields.Date(string='Date de début', tracking=True)
    end_date = fields.Date(string='Date de fin prévue', tracking=True)
    actual_end_date = fields.Date(string='Date de livraison effective')
    deadline = fields.Date(string='Date limite client', tracking=True)

    # ─── Budget & facturation ─────────────────────────────────────────────────
    budget = fields.Monetary(
        string='Budget (€)',
        currency_field='currency_id',
        tracking=True,
    )
    amount_invoiced = fields.Monetary(
        string='Montant facturé (€)',
        currency_field='currency_id',
        compute='_compute_amount_invoiced',
        store=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Devise',
        default=lambda self: self.env.company.currency_id,
    )

    # ─── Avancement ───────────────────────────────────────────────────────────
    progress = fields.Integer(
        string='Avancement (%)',
        default=0,
        tracking=True,
    )

    # ─── Équipe ───────────────────────────────────────────────────────────────
    team_lead_id = fields.Many2one(
        'res.users',
        string='Chef de projet',
        tracking=True,
        default=lambda self: self.env.user,
    )
    developer_ids = fields.Many2many(
        'res.users',
        'timz_project_developer_rel',
        'project_id',
        'user_id',
        string='Développeurs',
    )

    # ─── Workflow ─────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('in_progress', 'En cours'),
        ('review', 'En revue client'),
        ('delivered', 'Livré'),
        ('invoiced', 'Facturé'),
        ('cancelled', 'Annulé'),
    ], string='État', default='draft', tracking=True,
       group_expand='_expand_states', index=True)

    kanban_state = fields.Selection([
        ('normal', 'En cours'),
        ('done', 'Prêt pour validation'),
        ('blocked', 'Bloqué'),
    ], string='État Kanban', default='normal', tracking=True)

    # ─── Relations modules standards ─────────────────────────────────────────
    odoo_project_id = fields.Many2one(
        'project.project',
        string='Projet (module Project)',
        readonly=True,
        copy=False,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Bon de commande',
        readonly=True,
    )
    invoice_ids = fields.Many2many(
        'account.move',
        'timz_project_invoice_rel',
        'project_id',
        'invoice_id',
        string='Factures',
        domain=[('move_type', 'in', ['out_invoice', 'out_refund'])],
    )

    # ─── Computed ─────────────────────────────────────────────────────────────
    invoice_count = fields.Integer(
        string='Nb. Factures',
        compute='_compute_invoice_count',
    )
    task_count = fields.Integer(
        string='Nb. Tâches',
        compute='_compute_task_count',
    )

    # ─── Séquence ─────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('Nouveau')) == _('Nouveau'):
                vals['reference'] = (
                    self.env['ir.sequence'].next_by_code('timz.web.project')
                    or _('Nouveau')
                )
        return super().create(vals_list)

    # ─── Computed methods ──────────────────────────────────────────────────────
    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    @api.depends('invoice_ids', 'invoice_ids.amount_total', 'invoice_ids.state')
    def _compute_amount_invoiced(self):
        for rec in self:
            confirmed = rec.invoice_ids.filtered(lambda inv: inv.state == 'posted')
            rec.amount_invoiced = sum(confirmed.mapped('amount_total'))

    def _compute_task_count(self):
        for rec in self:
            if rec.odoo_project_id:
                rec.task_count = self.env['project.task'].search_count([
                    ('project_id', '=', rec.odoo_project_id.id)
                ])
            else:
                rec.task_count = 0

    @api.model
    def _expand_states(self, states, domain, order):
        return [key for key, _val in self._fields['state'].selection]

    # ─── Actions de workflow ──────────────────────────────────────────────────
    def action_start(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Seuls les projets en brouillon peuvent être démarrés."))
            rec.state = 'in_progress'
            rec.start_date = fields.Date.today()
            if not rec.odoo_project_id:
                odoo_project = self.env['project.project'].create({
                    'name': rec.name,
                    'partner_id': rec.client_id.id,
                    'user_id': rec.team_lead_id.id if rec.team_lead_id else False,
                    'date_start': rec.start_date,
                    'date': rec.deadline,
                })
                rec.odoo_project_id = odoo_project.id
            rec.message_post(
                body=_("Projet démarré. Projet Odoo « %s » créé.") % rec.odoo_project_id.name
            )

    def action_submit_review(self):
        for rec in self:
            if rec.state != 'in_progress':
                raise UserError(_("Le projet doit être en cours pour passer en revue client."))
            rec.state = 'review'
            rec.progress = 90
            rec.message_post(body=_("Projet soumis à la revue client."))

    def action_deliver(self):
        for rec in self:
            if rec.state != 'review':
                raise UserError(_("Le projet doit être en revue client avant d'être livré."))
            rec.state = 'delivered'
            rec.actual_end_date = fields.Date.today()
            rec.progress = 100
            rec.message_post(body=_("Projet livré au client le %s.") % rec.actual_end_date)

    def action_create_invoice(self):
        self.ensure_one()
        if self.state not in ('delivered', 'invoiced'):
            raise UserError(_("Le projet doit être livré avant de créer une facture."))
        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                "Aucun journal de vente trouvé pour la société '%s'.\n"
                "Allez dans Facturation → Configuration → Journaux et créez "
                "un journal de type 'Ventes'."
            ) % self.env.company.name)
        # Recherche d'un compte de revenus (prestations de service)
        income_account = self.env['account.account'].search([
            ('account_type', 'in', ['income', 'income_other']),
            ('company_id', '=', self.env.company.id),
            ('deprecated', '=', False),
        ], limit=1)
        if not income_account:
            # Fallback : compte de produits du journal lui-même
            income_account = journal.default_account_id
        if not income_account:
            raise UserError(_(
                "Aucun compte de revenus trouvé.\n"
                "Installez un plan comptable (Apps → 'Localisation France') "
                "ou créez manuellement un compte de type 'Revenus' dans "
                "Comptabilité → Configuration → Plan comptable."
            ))
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.client_id.id,
            'invoice_date': fields.Date.today(),
            'ref': self.reference,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': f'Prestation de développement web – {self.name}',
                'quantity': 1.0,
                'price_unit': self.budget,
                'account_id': income_account.id,
            })],
        })
        self.invoice_ids = [(4, invoice.id)]
        if self.state == 'delivered':
            self.state = 'invoiced'
        self.message_post(
            body=_("Facture %s créée pour un montant de %s €.") % (invoice.name, self.budget)
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        for rec in self:
            if rec.state == 'invoiced':
                raise UserError(_("Un projet facturé ne peut pas être annulé."))
            rec.state = 'cancelled'
            rec.message_post(body=_("Projet annulé."))

    def action_reset_draft(self):
        for rec in self:
            if rec.state == 'cancelled':
                rec.state = 'draft'
                rec.message_post(body=_("Projet remis en brouillon."))

    # ─── Smart buttons ────────────────────────────────────────────────────────
    def action_view_tasks(self):
        self.ensure_one()
        if not self.odoo_project_id:
            raise UserError(_("Aucun projet Odoo associé. Démarrez le projet d'abord."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'list,form,kanban',
            'domain': [('project_id', '=', self.odoo_project_id.id)],
            'context': {'default_project_id': self.odoo_project_id.id},
            'name': _('Tâches – %s') % self.name,
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'name': _('Factures – %s') % self.name,
        }

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref('timz_web_project.action_report_timz_project').report_action(self)

    # ─── Contraintes ──────────────────────────────────────────────────────────
    @api.constrains('progress')
    def _check_progress(self):
        for rec in self:
            if rec.progress < 0 or rec.progress > 100:
                raise ValidationError(
                    _("L'avancement doit être compris entre 0 et 100%%.")
                )

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(
                    _("La date de fin ne peut pas être antérieure à la date de début.")
                )

    @api.constrains('budget')
    def _check_budget(self):
        for rec in self:
            if rec.budget is not False and rec.budget < 0:
                raise ValidationError(_("Le budget ne peut pas être négatif."))
