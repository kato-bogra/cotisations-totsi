import os
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

def format_money(val: float, devise: str = "FCFA") -> str:
    return f"{val:,.0f} {devise}".replace(",", " ")

def generate_financial_pdf(db_conn, annee: int) -> bytes:
    cursor = db_conn.cursor()

    # Paramètres
    cursor.execute("SELECT cle, valeur FROM parametres")
    params = {row["cle"]: row["valeur"] for row in cursor.fetchall()}
    nom_groupe = params.get("nom_groupe", "Fraternité Sacerdotale")
    montant_annuel = float(params.get("montant_annuel", "10000"))
    devise = params.get("devise", "FCFA")

    # Données des membres et cotisations pour l'année
    cursor.execute("""
    SELECT u.id, u.nom_prenom, u.telephone, u.email,
           COALESCE(SUM(c.montant), 0) as total_verse,
           MAX(c.date_paiement) as derniere_date
    FROM users u
    LEFT JOIN cotisations c ON u.id = c.user_id AND c.annee = ?
    GROUP BY u.id
    ORDER BY u.nom_prenom ASC
    """, (annee,))
    membres = cursor.fetchall()

    # Données des dépenses
    cursor.execute("""
    SELECT d.id, d.titre, d.description, d.montant, d.date_depense, d.categorie, u.nom_prenom as auteur
    FROM depenses d
    LEFT JOIN users u ON d.enregistre_par_id = u.id
    ORDER BY d.date_depense DESC
    LIMIT 15
    """)
    depenses = cursor.fetchall()

    # Totaux globaux
    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM cotisations")
    total_cotisations_global = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM depenses")
    total_depenses_global = cursor.fetchone()["total"]

    avoir_en_caisse = total_cotisations_global - total_depenses_global

    # Totaux de l'année sélectionnée
    cursor.execute("SELECT COALESCE(SUM(montant), 0) as total FROM cotisations WHERE annee = ?", (annee,))
    total_cotisations_annee = cursor.fetchone()["total"]

    total_membres = len(membres)
    total_attendu_annee = total_membres * montant_annuel
    membres_a_jour = sum(1 for m in membres if m["total_verse"] >= montant_annuel)
    membres_partiels = sum(1 for m in membres if 0 < m["total_verse"] < montant_annuel)
    membres_non_regle = sum(1 for m in membres if m["total_verse"] == 0)

    # Création du document PDF en mémoire
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm
    )

    styles = getSampleStyleSheet()

    # Styles personnalisés
    header_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1E293B')
    )
    sub_header = ParagraphStyle(
        'SubHeader',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#475569')
    )
    section_title = ParagraphStyle(
        'SectionTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=12,
        spaceAfter=6
    )
    body_bold = ParagraphStyle(
        'BodyBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#1E293B')
    )
    body_text = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155')
    )
    badge_green = ParagraphStyle(
        'BadgeGreen',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#15803D')
    )
    badge_orange = ParagraphStyle(
        'BadgeOrange',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#C2410C')
    )
    badge_red = ParagraphStyle(
        'BadgeRed',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#B91C1C')
    )

    elements = []

    # En-tête avec logo de la Paroisse de Totsi
    logo_path = os.path.join(os.path.dirname(__file__), "static", "logo-totsi.jpg")
    if os.path.exists(logo_path):
        logo_img = RLImage(logo_path, width=2.4*cm, height=2.2*cm)
        header_text = [
            Paragraph(nom_groupe.upper(), ParagraphStyle('HTitle', parent=header_style, alignment=TA_LEFT, fontSize=15, leading=18)),
            Spacer(1, 2),
            Paragraph(f"ÉTAT FINANCIER DES COTISATIONS — EXERCICE {annee}", ParagraphStyle('HSub', parent=sub_header, alignment=TA_LEFT, fontName='Helvetica-Bold', fontSize=10.5, textColor=colors.HexColor('#4338CA'))),
            Spacer(1, 2),
            Paragraph(f"Document officiel généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", ParagraphStyle('HDate', parent=sub_header, alignment=TA_LEFT, fontSize=8, textColor=colors.HexColor('#64748B')))
        ]
        header_table = Table([[logo_img, header_text]], colWidths=[2.7*cm, 15.3*cm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (1, 0), (1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(header_table)
    else:
        elements.append(Paragraph(nom_groupe.upper(), header_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"ÉTAT FINANCIER DES COTISATIONS — EXERCICE {annee}", ParagraphStyle(
            'DocSub', parent=sub_header, fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#4338CA')
        )))
        elements.append(Paragraph(f"Document officiel généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", sub_header))

    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#CBD5E1"), spaceAfter=10))

    # Bloc 1 : Synthèse de la Caisse
    elements.append(Paragraph("1. SYNTHÈSE DE LA CAISSE & SITUATION GÉNÉRALE", section_title))
    
    kpi_data = [
        [
            Paragraph("<b>AVOIR NET EN CAISSE :</b>", body_bold),
            Paragraph(f"<font color='#047857' size='11'><b>{format_money(avoir_en_caisse, devise)}</b></font>", body_bold),
            Paragraph("<b>Cotisation annuelle par prêtre :</b>", body_bold),
            Paragraph(f"<b>{format_money(montant_annuel, devise)}</b>", body_bold)
        ],
        [
            Paragraph("Cotisations perçues (Total Caisse) :", body_text),
            Paragraph(format_money(total_cotisations_global, devise), body_text),
            Paragraph(f"Cotisations perçues ({annee}) :", body_text),
            Paragraph(format_money(total_cotisations_annee, devise), body_text)
        ],
        [
            Paragraph("Dépenses totales déduites :", body_text),
            Paragraph(f"<font color='#B91C1C'>{format_money(total_depenses_global, devise)}</font>", body_text),
            Paragraph(f"Taux de recouvrement ({annee}) :", body_text),
            Paragraph(f"<b>{(total_cotisations_annee / total_attendu_annee * 100 if total_attendu_annee > 0 else 0):.1f} %</b> ({membres_a_jour}/{total_membres} à jour)", body_text)
        ]
    ]

    kpi_table = Table(kpi_data, colWidths=[5.0*cm, 3.8*cm, 5.0*cm, 3.8*cm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 10))

    # Bloc 2 : Situation individuelle des membres
    elements.append(Paragraph(f"2. STATUT INDIVIDUEL DES CONFRÈRES (ANNÉE {annee})", section_title))

    col_headers = [
        Paragraph("<b>N°</b>", body_bold),
        Paragraph("<b>Nom du Confrère</b>", body_bold),
        Paragraph("<b>Téléphone</b>", body_bold),
        Paragraph("<b>Exigible</b>", body_bold),
        Paragraph("<b>Versé</b>", body_bold),
        Paragraph("<b>Reste</b>", body_bold),
        Paragraph("<b>Statut</b>", body_bold),
    ]
    members_data = [col_headers]

    for idx, m in enumerate(membres, start=1):
        verse = float(m["total_verse"])
        reste = max(0.0, montant_annuel - verse)
        
        if verse >= montant_annuel:
            statut_p = Paragraph("À JOUR", badge_green)
            bg_row = colors.HexColor('#F0FDF4') if idx % 2 == 0 else colors.white
        elif verse > 0:
            statut_p = Paragraph(f"PARTIEL (-{format_money(reste, devise)})", badge_orange)
            bg_row = colors.HexColor('#FFFBEB') if idx % 2 == 0 else colors.white
        else:
            statut_p = Paragraph("NON RÉGLÉ", badge_red)
            bg_row = colors.HexColor('#FEF2F2') if idx % 2 == 0 else colors.white

        row = [
            Paragraph(str(idx), body_text),
            Paragraph(f"<b>{m['nom_prenom']}</b>", body_text),
            Paragraph(m['telephone'] or "-", body_text),
            Paragraph(format_money(montant_annuel, devise), body_text),
            Paragraph(f"<b>{format_money(verse, devise)}</b>", body_text),
            Paragraph(format_money(reste, devise), body_text),
            statut_p
        ]
        members_data.append(row)

    # Ligne de total
    tot_verse_sum = sum(float(m["total_verse"]) for m in membres)
    tot_reste_sum = sum(max(0.0, montant_annuel - float(m["total_verse"])) for m in membres)
    members_data.append([
        Paragraph("", body_bold),
        Paragraph("<b>TOTAL GÉNÉRAL</b>", body_bold),
        Paragraph("", body_bold),
        Paragraph(f"<b>{format_money(total_attendu_annee, devise)}</b>", body_bold),
        Paragraph(f"<b>{format_money(tot_verse_sum, devise)}</b>", body_bold),
        Paragraph(f"<b>{format_money(tot_reste_sum, devise)}</b>", body_bold),
        Paragraph(f"<b>{membres_a_jour}/{total_membres} Réglés</b>", body_bold),
    ])

    members_table = Table(
        members_data,
        colWidths=[0.8*cm, 5.2*cm, 2.7*cm, 2.3*cm, 2.3*cm, 2.2*cm, 2.5*cm]
    )
    members_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#94A3B8')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    # Forcer texte blanc sur header
    for c in range(len(col_headers)):
        members_table.setStyle(TableStyle([
            ('TEXTCOLOR', (c, 0), (c, 0), colors.white)
        ]))

    elements.append(members_table)
    elements.append(Spacer(1, 10))

    # Bloc 3 : Dépenses récentes (si existantes)
    if depenses:
        elements.append(Paragraph("3. DÉPENSES RÉCENTES DÉDUITES DE LA CAISSE", section_title))
        dep_headers = [
            Paragraph("<b>Date</b>", body_bold),
            Paragraph("<b>Motif / Désignation</b>", body_bold),
            Paragraph("<b>Catégorie</b>", body_bold),
            Paragraph("<b>Montant Déduit</b>", body_bold),
        ]
        dep_data = [dep_headers]
        for d in depenses:
            dep_data.append([
                Paragraph(d["date_depense"], body_text),
                Paragraph(f"<b>{d['titre']}</b><br/><font color='#64748B' size='7'>{d['description'] or ''}</font>", body_text),
                Paragraph(d["categorie"] or "Divers", body_text),
                Paragraph(f"<font color='#B91C1C'><b>-{format_money(d['montant'], devise)}</b></font>", body_text)
            ])
        dep_table = Table(dep_data, colWidths=[2.5*cm, 8.5*cm, 3.5*cm, 3.5*cm])
        dep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(dep_table)
        elements.append(Spacer(1, 12))

    # Signatures
    elements.append(KeepTogether([
        Spacer(1, 10),
        Paragraph("<i>« Comme il est bon, comme il est doux pour des frères d'habiter ensemble ! » (Psaume 133, 1)</i>", ParagraphStyle(
            'Quote', parent=styles['Normal'], fontName='Helvetica-Oblique', fontSize=8.5, alignment=TA_CENTER, textColor=colors.HexColor('#64748B')
        )),
        Spacer(1, 15),
        Table([
            [
                Paragraph("<b>L'Économe</b><br/><br/><br/><i>Pour visa et certification</i>", ParagraphStyle('Sign1', parent=body_text, alignment=TA_CENTER)),
                Paragraph("<b>Le Trésorier</b><br/><br/><br/><i>Pour arrêté des comptes</i>", ParagraphStyle('Sign2', parent=body_text, alignment=TA_CENTER))
            ]
        ], colWidths=[9.0*cm, 9.0*cm], style=[
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBEFORE', (1, 0), (1, 0), 0.5, colors.HexColor('#E2E8F0'))
        ])
    ]))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
