{
    'name': 'Timz Web Project',
    'version': '17.0.1.0.0',
    'category': 'Project',
    'summary': 'Gestion des demandes clients et projets web — Timz & Co',
    'description': """
Timz Web Project
================
Module de gestion du cycle complet des projets web pour l'entreprise Timz & Co :
  - Saisie et qualification des demandes clients
  - Création automatique d'opportunités CRM et de devis
  - Suivi des projets web avec workflow d'états
  - Génération des factures
  - Rapport PDF de fiche projet
  - Tableau de bord statistique
    """,
    'author': 'MAHAMAT AHMAT TIMAN',
    'company': 'Timz & Co',
    'website': 'https://timzandco.com',
    'depends': [
        'base',
        'mail',
        'contacts',
        'crm',
        'sale_management',
        'project',
        'account',
    ],
    'data': [
        'security/timz_security.xml',
        'security/ir.model.access.csv',
        'data/timz_sequence_data.xml',
        'data/timz_products_data.xml',
        'views/timz_client_request_views.xml',
        'views/timz_web_project_views.xml',
        'views/timz_dashboard_views.xml',
        'views/timz_menus.xml',
        'reports/timz_project_report.xml',
        'reports/timz_project_report_template.xml',
    ],
    'assets': {},
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
