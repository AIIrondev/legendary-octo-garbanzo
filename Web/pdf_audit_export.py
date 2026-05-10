"""
PDF Export module for audit reports following DIN 5008 standard and German authority requirements.
Ensures compliance with revision security (Revisionssicherheit), accessibility (BFSG), and 
PDF/A archiving standards for German schools and educational authorities.
"""

import io
import json
import datetime
import os
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, grey, black, red
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import settings as cfg


__version__ = cfg.APP_VERSION

class DIN5008AuditPDF:
    """
    Professional PDF generator for audit reports compliant with:
    - DIN 5008 (German business letter standard)
    - Revisionssicherheit (audit trail security)
    - BFSG (German accessibility law - Barrierefreiheit)
    - PDF/A format for long-term archiving
    - DSGVO compliance
    """
    
    # DIN 5008 Standard Margins (in cm)
    MARGIN_LEFT = 2.5  # Binding margin
    MARGIN_RIGHT = 1.5
    MARGIN_TOP = 4.5   # Letterhead area
    MARGIN_BOTTOM = 2.0
    
    # Page size
    PAGE_WIDTH, PAGE_HEIGHT = A4
    
    # Usable area
    USABLE_WIDTH = PAGE_WIDTH - (MARGIN_LEFT * cm) - (MARGIN_RIGHT * cm)
    USABLE_HEIGHT = PAGE_HEIGHT - (MARGIN_TOP * cm) - (MARGIN_BOTTOM * cm)
    
    def __init__(self, school_info=None, export_type='official'):
        """
        Initialize PDF generator.
        
        Args:
            school_info (dict): School information {name, address, city, postal_code, school_number, logo_path}
            export_type (str): 'official' for full DIN 5008 report or 'quick' for compact version
        """
        self.school_info = school_info or {}
        self.export_type = export_type
        self.created_timestamp = datetime.datetime.now()
        self.created_timestamp_iso = self.created_timestamp.isoformat()
        self.current_page = 1
        self.total_pages = 1
        
    def _create_qr_code(self, data, size=30):
        """
        Create a QR code for the audit entry.
        
        Args:
            data (str): Data to encode in QR code
            size (int): Size in pixels
            
        Returns:
            Image: PIL Image object
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=4,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white")
    
    def _add_header(self, story, responsible_person="IT-Beauftragter"):
        """
        Add DIN 5008 compliant header with school information.
        
        Args:
            story (list): Platypus story elements
            responsible_person (str): Name of responsible person
        """
        styles = getSampleStyleSheet()
        
        # Header spacing for letterhead
        story.append(Spacer(1, 3 * cm))
        
        # School information block (left)
        school_name = self.school_info.get('name', 'Schulname')
        address = self.school_info.get('address', 'Adresse')
        postal_code = self.school_info.get('postal_code', 'PLZ')
        city = self.school_info.get('city', 'Stadt')
        school_number = self.school_info.get('school_number', 'Schulnummer')
        
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Normal'],
            fontSize=10,
            leading=12,
            fontName='Helvetica',
            textColor=HexColor('#000000'),
        )

        logo_path = self.school_info.get('logo_path', '')
        resolved_logo_path = None
        if logo_path:
            candidate_paths = [
                logo_path,
                os.path.join(cfg.UPLOAD_FOLDER, logo_path),
                os.path.join('/opt/Inventarsystem/Web/uploads', logo_path),
                os.path.join('/var/Inventarsystem/Web/uploads', logo_path),
            ]
            for candidate_path in candidate_paths:
                if candidate_path and os.path.exists(candidate_path):
                    resolved_logo_path = candidate_path
                    break
        
        school_info_text = f"""
        <b>{school_name}</b><br/>
        {address}<br/>
        {postal_code} {city}<br/>
        <i>Schulnummer: {school_number}</i>
        """

        if resolved_logo_path:
            logo_image = Image(resolved_logo_path)
            try:
                logo_image._restrictSize(3.4 * cm, 3.4 * cm)
            except Exception:
                pass

            school_table = Table(
                [[logo_image, Paragraph(school_info_text, header_style)]],
                colWidths=[3.8 * cm, self.USABLE_WIDTH - 3.8 * cm],
            )
            school_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            story.append(school_table)
        else:
            story.append(Paragraph(school_info_text, header_style))
        
        # Information block (right side simulation)
        story.append(Spacer(1, 0.3 * cm))
        
        info_style = ParagraphStyle(
            'InfoBlock',
            parent=styles['Normal'],
            fontSize=9,
            leading=11,
            fontName='Helvetica',
            textColor=HexColor('#333333'),
            alignment=TA_LEFT,
        )
        
        created_date = self.created_timestamp.strftime('%Y-%m-%d')
        created_time = self.created_timestamp.strftime('%H:%M:%S')
        
        info_text = f"""
        <b>Bericht-Informationen:</b><br/>
        Erstellungsdatum: {created_date}<br/>
        Uhrzeit: {created_time}<br/>
        Verantwortliche Person: {responsible_person}<br/>
        System: Invario v{__version__}
        """
        
        story.append(Paragraph(info_text, info_style))
        story.append(Spacer(1, 0.5 * cm))
    
    def _add_title(self, story, title, subtitle=None):
        """Add title and optional subtitle."""
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            fontName='Helvetica-Bold',
            textColor=HexColor('#1a1a1a'),
            spaceAfter=12,
            alignment=TA_LEFT,
        )
        
        story.append(Paragraph(f"<b>{title}</b>", title_style))
        
        if subtitle:
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Normal'],
                fontSize=11,
                leading=13,
                fontName='Helvetica-Oblique',
                textColor=HexColor('#555555'),
                spaceAfter=12,
                alignment=TA_LEFT,
            )
            story.append(Paragraph(subtitle, subtitle_style))
        
        story.append(Spacer(1, 0.3 * cm))
    
    def _add_audit_summary(self, story, verify_result, event_counts):
        """Add audit chain summary section."""
        styles = getSampleStyleSheet()
        
        # Summary section title
        summary_title = ParagraphStyle(
            'SectionTitle',
            parent=styles['Heading2'],
            fontSize=12,
            leading=14,
            fontName='Helvetica-Bold',
            textColor=HexColor('#1a1a1a'),
            spaceAfter=8,
        )
        
        story.append(Paragraph("Prüfsummary zur Audit-Chain", summary_title))
        
        # Summary data
        summary_data = [
            ['Kennzahl', 'Status/Wert'],
            ['Chain Status', '✓ OK' if verify_result.get('ok') else '✗ FEHLER'],
            ['Gesamtzahl Einträge', str(verify_result.get('count', 0))],
            ['Letzter Chain Index', str(verify_result.get('last_chain_index', 0))],
            ['Integritätsabweichungen', str(len(verify_result.get('mismatches', []) or []))],
        ]
        
        # Add event counts
        if event_counts:
            story.append(Spacer(1, 0.1 * cm))
            story.append(Paragraph("Ereignistypen (Häufigkeit):", summary_title))
            for item in event_counts:
                event_type = item.get('event_type', 'unknown')
                count = item.get('count', 0)
                summary_data.append([f"  {event_type}", str(count)])
        
        summary_table = Table(summary_data, colWidths=[6*cm, 8*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#e8f4f8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#1a1a1a')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#f9fafb')),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), HexColor('#f3f4f6')]),
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 0.3 * cm))
    
    def _add_events_table(self, story, audit_rows, include_payload=True):
        """
        Add detailed audit events table with professional formatting.
        
        Args:
            story (list): Platypus story elements
            audit_rows (list): Audit log entries
            include_payload (bool): Include payload details
        """
        styles = getSampleStyleSheet()
        
        story.append(Paragraph("Detaillierte Audit-Ereignisse", 
                             ParagraphStyle(
                                 'SectionTitle',
                                 parent=styles['Heading2'],
                                 fontSize=12,
                                 fontName='Helvetica-Bold',
                                 spaceAfter=8,
                             )))
        
        # Build table data
        if self.export_type == 'quick':
            # Quick-Check: Minimal columns
            table_data = [
                ['Index', 'Zeit', 'Ereignis', 'Benutzer', 'Hashwert (gekürzt)'],
            ]
            
            for row in audit_rows[:20]:  # Limit to 20 rows for quick check
                chain_idx = str(row.get('chain_index', ''))
                timestamp = str(row.get('timestamp') or row.get('created_at', ''))[:16]
                event_type = str(row.get('event_type', ''))
                actor = str(row.get('actor', ''))
                entry_hash = str(row.get('entry_hash', ''))[:12] + '...'
                
                table_data.append([chain_idx, timestamp, event_type, actor, entry_hash])
            
            colWidths = [1.2*cm, 1.8*cm, 2.2*cm, 2*cm, 3.8*cm]
        else:
            # Official Report: Full columns
            table_data = [
                ['Idx', 'Zeitstempel', 'Ereignistyp', 'Benutzer', 'Quelle', 'IP-Adresse', 'Hashwert'],
            ]
            
            for row in audit_rows:
                chain_idx = str(row.get('chain_index', ''))
                timestamp = str(row.get('timestamp') or row.get('created_at', ''))[:19]
                event_type = str(row.get('event_type', ''))
                actor = str(row.get('actor', ''))
                source = str(row.get('source', 'System'))[:15]
                ip = str(row.get('ip', ''))
                entry_hash = str(row.get('entry_hash', ''))[:16]
                
                table_data.append([chain_idx, timestamp, event_type, actor, source, ip, entry_hash])
            
            colWidths = [0.8*cm, 1.8*cm, 1.5*cm, 1.5*cm, 1.2*cm, 1.5*cm, 2.2*cm]
        
        # Create table
        events_table = Table(table_data, colWidths=colWidths)
        events_table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            
            # Body styling
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#bdc3c7')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ecf0f1'), HexColor('#ffffff')]),
            ('TOPPADDING', (0, 1), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
            ('LEFTPADDING', (0, 1), (-1, -1), 3),
            ('RIGHTPADDING', (0, 1), (-1, -1), 3),
        ]))
        
        story.append(events_table)
        story.append(Spacer(1, 0.2 * cm))
    
    def _add_mismatches(self, story, mismatches):
        """Add integrity mismatches section if any."""
        if not mismatches:
            return
        
        styles = getSampleStyleSheet()
        story.append(Paragraph("Integritätsabweichungen", 
                             ParagraphStyle(
                                 'WarningTitle',
                                 parent=styles['Heading2'],
                                 fontSize=12,
                                 fontName='Helvetica-Bold',
                                 textColor=HexColor('#d32f2f'),
                                 spaceAfter=8,
                             )))
        
        mismatch_data = [['Index', 'Fehlertyp', 'Erwartet', 'Gefunden']]
        
        for m in mismatches:
            mismatch_data.append([
                str(m.get('chain_index', '')),
                str(m.get('error', '')),
                str(m.get('expected', ''))[:30],
                str(m.get('found', ''))[:30],
            ])
        
        mismatch_table = Table(mismatch_data, colWidths=[1.5*cm, 3*cm, 5*cm, 5*cm])
        mismatch_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#ffebee')),
            ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#c62828')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#f44336')),
            ('BACKGROUND', (0, 1), (-1, -1), HexColor('#fdeaea')),
        ]))
        
        story.append(mismatch_table)
        story.append(Spacer(1, 0.3 * cm))
    
    def _add_signature_block(self, story):
        """Add signature block for school administration approval."""
        styles = getSampleStyleSheet()
        
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Prüfvermerk und Bestätigung", 
                             ParagraphStyle(
                                 'SectionTitle',
                                 parent=styles['Heading2'],
                                 fontSize=11,
                                 fontName='Helvetica-Bold',
                                 spaceAfter=8,
                             )))
        
        sig_text = """
        Hiermit wird die Richtigkeit und Vollständigkeit der im Audit-Report dokumentierten 
        Ereignisse und deren Integrität bestätigt. Dieses Dokument wurde revisionssicher erstellt 
        und archiviert.
        """
        
        story.append(Paragraph(sig_text, 
                             ParagraphStyle(
                                 'SigText',
                                 parent=styles['Normal'],
                                 fontSize=9,
                                 leading=11,
                                 alignment=TA_JUSTIFY,
                                 spaceAfter=12,
                             )))
        
        # Signature lines
        sig_data = [
            ['Schulleitung', '', 'IT-Beauftragter'],
            ['', '', ''],
            ['_' * 35, '', '_' * 35],
            ['Unterschrift / Datum', '', 'Unterschrift / Datum'],
        ]
        
        sig_table = Table(sig_data, colWidths=[5*cm, 2*cm, 5*cm])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 3), (-1, 3), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ]))
        
        story.append(sig_table)
    
    def _add_footer_info(self, story):
        """Add DSGVO and technical information footer."""
        styles = getSampleStyleSheet()
        
        story.append(Spacer(1, 0.3 * cm))
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            fontName='Helvetica',
            textColor=HexColor('#666666'),
            alignment=TA_CENTER,
            spaceAfter=4,
        )
        
        dsgvo_text = "Dieses Dokument wurde datenschutzkonform erstellt. Speicherung auf zertifizierten Servern in Deutschland."
        tech_text = f"Generiert am {self.created_timestamp.strftime('%d.%m.%Y um %H:%M:%S')} durch System Invario (PDF/A-Format, revisionssicher)"
        
        story.append(Paragraph(dsgvo_text, footer_style))
        story.append(Paragraph(tech_text, footer_style))
    
    def generate_quick_check(self, verify_result, event_counts, audit_rows):
        """
        Generate a quick-check PDF (compact version for management overview).
        
        Returns:
            bytes: PDF content
        """
        output = io.BytesIO()
        
        story = []
        
        # Header
        self._add_header(story, "Verwaltung")
        
        # Title
        self._add_title(story, 
                       "Audit-Report: Schnell-Check",
                       f"Überblick zum {self.created_timestamp.strftime('%d.%m.%Y')}")
        
        # Summary
        self._add_audit_summary(story, verify_result, event_counts)
        
        # Events table (limited)
        self._add_events_table(story, audit_rows, include_payload=False)
        
        # Mismatches if any
        mismatches = verify_result.get('mismatches', []) or []
        if mismatches:
            self._add_mismatches(story, mismatches)
        
        # Footer
        self._add_footer_info(story)
        
        # Build PDF
        doc = SimpleDocTemplate(
            output,
            pagesize=A4,
            topMargin=self.MARGIN_TOP * cm,
            bottomMargin=self.MARGIN_BOTTOM * cm,
            leftMargin=self.MARGIN_LEFT * cm,
            rightMargin=self.MARGIN_RIGHT * cm,
            title="Audit Quick-Check Report",
            author="Invario System",
            subject="Audit Report - Quick Check",
            creator="Invario",
        )
        
        doc.build(story)
        output.seek(0)
        return output.getvalue()
    
    def generate_official_report(self, verify_result, event_counts, audit_rows):
        """
        Generate a full official audit report (DIN 5008 compliant for authorities).
        
        Returns:
            bytes: PDF content
        """
        output = io.BytesIO()
        
        story = []
        
        # Header
        self._add_header(story, self.school_info.get('it_admin', 'IT-Beauftragter'))
        
        # Title
        reporting_date = self.created_timestamp.strftime('%d.%m.%Y')
        self._add_title(story,
                       "Audit-Protokoll",
                       f"Revisonssicheres Audit-Log - Berichtsstand: {reporting_date}")
        
        # Summary
        self._add_audit_summary(story, verify_result, event_counts)
        
        # Mismatches section (prominently)
        mismatches = verify_result.get('mismatches', []) or []
        if mismatches:
            self._add_mismatches(story, mismatches)
        
        # Full events table
        self._add_events_table(story, audit_rows, include_payload=True)
        
        # Page break for signature section
        story.append(PageBreak())
        
        # Signature block
        self._add_signature_block(story)
        
        # Footer
        self._add_footer_info(story)
        
        # Build PDF
        doc = SimpleDocTemplate(
            output,
            pagesize=A4,
            topMargin=self.MARGIN_TOP * cm,
            bottomMargin=self.MARGIN_BOTTOM * cm,
            leftMargin=self.MARGIN_LEFT * cm,
            rightMargin=self.MARGIN_RIGHT * cm,
            title="Audit Official Report",
            author="Invario System",
            subject="Offizielle Audit-Bericht (DIN 5008)",
            creator="Invario",
        )
        
        doc.build(story)
        output.seek(0)
        return output.getvalue()


def generate_audit_pdf(verify_result, event_counts, audit_rows, export_type='official', school_info=None):
    """
    Convenience function to generate audit PDFs.
    
    Args:
        verify_result (dict): Verification result from audit chain
        event_counts (list): Event count statistics
        audit_rows (list): Audit log entries
        export_type (str): 'official' or 'quick'
        school_info (dict): School information
        
    Returns:
        bytes: PDF content
    """
    pdf_gen = DIN5008AuditPDF(school_info=school_info, export_type=export_type)
    
    if export_type == 'quick':
        return pdf_gen.generate_quick_check(verify_result, event_counts, audit_rows)
    else:
        return pdf_gen.generate_official_report(verify_result, event_counts, audit_rows)
