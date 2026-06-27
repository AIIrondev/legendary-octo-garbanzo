from flask import Blueprint, render_template, request, session, url_for, redirect, flash, make_response, Response, send_file
import Web.modules.terminplaner.backend_server as appointment_service
import Web.modules.database.settings as cfg
import Web.modules.database.termine as termin
import Web.modules.database.user as us
from Web.modules.terminplaner.backend_server import _resolve_public_base_url
import csv
import io
import qrcode
import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import grey, HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image


# Create a blueprint instance
appoint_bp = Blueprint('terminplaner', __name__)


def _get_school_info_for_export():
    """
    Get school information for PDF exports from configuration or database.
    Returns default info if not configured.
    """
    try:
        if hasattr(cfg, 'get_school_info'):
            return cfg.get_school_info()

        school_info = {
            'name': 'Schulname',
            'address': 'Schuladresse',
            'postal_code': 'PLZ',
            'city': 'Stadt',
            'school_number': '000000',
            'it_admin': 'IT-Beauftragter/in',
            'logo_path': '',
        }
        return school_info
    except Exception:
        # Return defaults if anything fails
        return {
            'name': 'Schulname',
            'address': 'Schuladresse', 
            'postal_code': 'PLZ',
            'city': 'Stadt',
            'school_number': '000000',
            'it_admin': 'IT-Beauftragter/in',
            'logo_path': '',
        }


def _require_module_enabled():
    if not cfg.MODULES.is_enabled('terminplan'):
        flash('Der Terminplaner ist deaktiviert.', 'info')
        return redirect(url_for('home'))
    return None


def _appointment_not_found_response():
    return render_template(
        'terminplaner_not_found.html',
        error_code=404,
        error_message='Der Termin wurde nicht gefunden.',
    ), 404


def _current_tenant_id():
    try:
        from Web.tenant import get_tenant_context
        ctx = get_tenant_context()
        if ctx and getattr(ctx, 'tenant_id', None):
            return str(ctx.tenant_id)
    except Exception:
        pass
    return str(session.get('tenant_id', '') or '').strip()

@appoint_bp.route('/client/<appointment_id>/export_csv')
def export_csv(appointment_id):
    """
    Generiert einen CSV-Export aller Buchungen für den Ersteller.
    """
    # 1. Berechtigungsprüfung (analog zur Client-Route)
    current_user = str(session.get('username', '') or '').strip()
    appointment_item = termin.get_item(appointment_id) or {}
    appointment_owner = str(appointment_item.get('user', '') or '').strip()
    
    can_view = False
    if current_user:
        try:
            can_view = bool(us.check_admin(current_user) or current_user == appointment_owner)
        except Exception:
            can_view = bool(current_user == appointment_owner)
            
    if not can_view:
        flash('Nicht autorisiert für diesen Export.', 'error')
        return redirect(url_for('terminplaner.client', appointment_id=appointment_id))

    custom_fields = appointment_item.get('custom_fields', [])
    bookings = appointment_item.get('slots_booked', []) or []

    # 2. CSV im Speicher erstellen
    si = io.StringIO()
    # Wir nutzen ein Semikolon als Trennzeichen – das öffnet Excel im deutschsprachigen Raum direkt fehlerfrei
    cw = csv.writer(si, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    
    # Tabellenkopf schreiben
    headers = ['Zeitpunkt', 'Name'] + list(custom_fields)
    cw.writerow(headers)
    
    # Datenzeilen schreiben
    for booking in bookings:
        if isinstance(booking, (list, tuple)):
            row = [booking[0], booking[1]]
            
            # Antworten holen und sicherstellen, dass Lücken (falls vorhanden) mit Leerstrings gefüllt werden
            answers = booking[2] if len(booking) > 2 else []
            for i in range(len(custom_fields)):
                if i < len(answers):
                    row.append(answers[i])
                else:
                    row.append('')
            cw.writerow(row)

    # 3. Response vorbereiten und UTF-8-BOM für Excel mitsenden
    response_content = si.getvalue()
    output = make_response(response_content)
    
    output.data = b'\xef\xbb\xbf' + output.data
    
    # Dateiname generieren
    title_slug = appointment_item.get('title', 'export').replace(' ', '_')
    output.headers["Content-Disposition"] = f"attachment; filename=buchungen_{title_slug}.csv"
    output.headers["Content-Type"] = "text/csv; charset=utf-8"
    
    return output

@appoint_bp.route('/client/<appointment_id>', methods=['POST', 'GET'])
def client(appointment_id):
    """
    The Route for the terminplaner to work with the client and allow owners to manage it.
    """
    guard = _require_module_enabled()
    if guard:
        return guard

    available = appointment_service.get_available(appointment_id)
    if not available:
        return _appointment_not_found_response()

    current_user = str(session.get('username', '') or '').strip()
    appointment_item = termin.get_item(appointment_id) or {}
    appointment_owner = str(appointment_item.get('user', '') or '').strip()
    
    custom_fields = appointment_item.get('custom_fields', [])

    # Permissions check
    can_view_booking_names = False
    if current_user:
        try:
            can_view_booking_names = bool(us.check_admin(current_user) or current_user == appointment_owner)
        except Exception:
            can_view_booking_names = bool(current_user == appointment_owner)

    # Sanitize data for public/client view
    available_for_view = dict(available)
    if not can_view_booking_names:
        sanitized_bookings = []
        for booking in (available.get('slots_booked') or []):
            if isinstance(booking, dict):
                sanitized_bookings.append({'start': booking.get('start', '')})
            elif isinstance(booking, (list, tuple)) and len(booking) >= 1:
                sanitized_bookings.append({'start': booking[0]})
            else:
                sanitized_bookings.append({'start': ''})
        available_for_view['slots_booked'] = sanitized_bookings

    if request.method == 'POST':
        action = request.form.get('action', 'book')

        # Case 1: Admin/Owner cancels a booking
        if action == 'delete' and can_view_booking_names:
            slot_time = request.form.get('slot_time')
            client_name = request.form.get('target_client_name')
            
            current_slots = appointment_item.get('slots_booked', []) or []
            
            # Keep everything EXCEPT the item targeted for deletion
            updated_slots = [
                slot for slot in current_slots 
                if not (isinstance(slot, (list, tuple)) and slot[0] == slot_time and slot[1] == client_name)
            ]
            
            if termin.update(appointment_id, updated_slots):
                flash('Buchung wurde erfolgreich gelöscht.', 'success')
            else:
                flash('Fehler beim Löschen der Buchung.', 'error')
                
            return redirect(url_for('terminplaner.client', appointment_id=appointment_id, tenant=_current_tenant_id() or None))

        # Case 2: Client books a slot
        elif action == 'book':
            start_daytime = request.form.get('start_day_time')
            username = request.form.get('client_name')
            custom_answers = tuple(request.form.getlist('custom_answers'))  # Cast to tuple for DB safety

            if not start_daytime or not username:
                flash('Bitte Name und gewünschte Uhrzeit angeben.', 'error')
                return render_template(
                    'termin_client.html',
                    appointment_id=appointment_id,
                    available=available_for_view,
                    current_user=session.get('username', ''),
                    tenant_id=_current_tenant_id(),
                    can_view_booking_names=can_view_booking_names,
                    custom_fields=custom_fields 
                )

            if appointment_service.book_slot(appointment_id, start_daytime, username, custom=custom_answers):
                return redirect(
                    url_for(
                        'terminplaner.client_success',
                        appointment_id=appointment_id,
                        tenant=_current_tenant_id() or None,
                        start=start_daytime,
                        name=username,
                    )
                )

            flash('Der Termin konnte nicht gespeichert werden. Eventuell ist der Slot bereits voll.', 'error')

    return render_template(
        'termin_client.html',
        appointment_id=appointment_id,
        available=available_for_view,
        current_user=session.get('username', ''),
        tenant_id=_current_tenant_id(),
        can_view_booking_names=can_view_booking_names,
        custom_fields=custom_fields,
        appointment_item=appointment_item
    )


@appoint_bp.route('/client/success/<appointment_id>', methods=['GET'])
def client_success(appointment_id):
    guard = _require_module_enabled()
    if guard:
        return guard

    slot_start = str(request.args.get('start', '') or '').strip()
    client_name = str(request.args.get('name', '') or '').strip()

    return render_template(
        'termin_client_success.html',
        appointment_id=appointment_id,
        slot_start=slot_start,
        client_name=client_name,
        tenant_id=_current_tenant_id(),
    )


@appoint_bp.route('/delete/<appointment_id>', methods=['POST'])
def delete_appointment(appointment_id):
    guard = _require_module_enabled()
    if guard:
        return guard

    if 'username' not in session:
        flash('Bitte mit einem Konto anmelden.', 'error')
        return redirect(url_for('login'))

    appointment = termin.get_item(appointment_id)
    if not appointment:
        return _appointment_not_found_response()

    current_user = str(session.get('username', '')).strip()
    appointment_user = str(appointment.get('user', '')).strip()
    if not us.check_admin(current_user) and appointment_user != current_user:
        flash('Sie dürfen diesen Termin nicht löschen.', 'error')
        return redirect(url_for('terminplaner.main', tenant=_current_tenant_id() or None))

    if termin.remove(appointment_id):
        flash('Der Terminplan wurde gelöscht.', 'success')
    else:
        flash('Der Terminplan konnte nicht gelöscht werden.', 'error')

    return redirect(url_for('terminplaner.main', tenant=_current_tenant_id() or None))

@appoint_bp.route('/configure', methods=['GET', 'POST'])
def configure():
    """
    Route for authenticated persons to configure a new appointment schedule
    """
    guard = _require_module_enabled()
    if guard:
        return guard

    if 'username' not in session:
        flash('Bitte mit einem Konto anmelden.', 'error')
        return redirect(url_for('login'))

    if request.method == "POST":
        start = request.form.get('start_date')
        end = request.form.get('end_date')
        time = request.form.get('time_frame')
        slots_amount = request.form.get('slots_amounts')
        slot_length = request.form.get('slot_length') 
        mail = request.form.get('mail', '')
        note = request.form.get('note', '')
        add_to_calendar = request.form.get('add_to_calendar') == 'on'
        title = request.form.get('title', '').strip()
        custom = request.form.getlist('custom_fields')
        
        try:
            clients_p_slot = int(request.form.get('clients_per_slot', 1))
        except (ValueError, TypeError):
            clients_p_slot = 1

        if not start or not end or not time or not slots_amount or not slot_length or not title:
            flash('Bitte alle Pflichtfelder ausfüllen.', 'error')
            return render_template(
                'termin_configure.html',
                school_periods=cfg.SCHOOL_PERIODS,
                generated_link=None,
                email_service_enabled=cfg.EMAIL_ENABLED,
            )

        # Call the database service function (standardized to match your underlying code)
        inserted_id = appointment_service.new(
            date_start=start, 
            date_end=end, 
            time_span=time, 
            slots=slots_amount, 
            slot_length=slot_length, 
            user=session["username"], 
            mail=mail, 
            note=note, 
            calendar_enabled=add_to_calendar, 
            title=title, 
            custom_fields=custom,
            clients_per_slot=clients_p_slot
        )

        if not inserted_id:
            flash('Fehler beim Erstellen des Terminplans.', 'error')
            return redirect(url_for('terminplaner.configure'))

        flash('Der Terminplan wurde angelegt.', 'success')
        return render_template(
            'termin_configure.html',
            school_periods=cfg.SCHOOL_PERIODS,
            generated_link=inserted_id['link'],
            calendar_link=None, 
            add_to_calendar=add_to_calendar,
            email_service_enabled=cfg.EMAIL_ENABLED,
            title=title,
        )

    return render_template(
        'termin_configure.html',
        school_periods=cfg.SCHOOL_PERIODS,
        generated_link=None,
        calendar_link=None,
        add_to_calendar=False,
        email_service_enabled=cfg.EMAIL_ENABLED,
        title=None,
    )


@appoint_bp.route('/calendar/<appointment_id>.ics', methods=['GET'])
def calendar_export(appointment_id):
    guard = _require_module_enabled()
    if guard:
        return guard

    ics_content = appointment_service.build_calendar_ics(appointment_id)
    if not ics_content:
        return _appointment_not_found_response()

    title = str(request.args.get('title', '') or '').strip() or appointment_id

    response = Response(ics_content, mimetype='text/calendar; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename=terminplan-{title}-{appointment_id}.ics'
    return response


@appoint_bp.route('/client_ics/<appointment_id>.ics', methods=['GET'])
def client_slot_calendar_export(appointment_id):
    guard = _require_module_enabled()
    if guard:
        return guard

    slot_start = str(request.args.get('start', '') or '').strip()
    client_name = str(request.args.get('name', '') or '').strip()
    ics_content = appointment_service.build_client_slot_ics(appointment_id, slot_start, client_name=client_name)
    if not ics_content:
        return _appointment_not_found_response()

    title = str(request.args.get('title', '') or '').strip() or appointment_id

    response = Response(ics_content, mimetype='text/calendar; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename=termin-{title}-{appointment_id}-{slot_start.replace(" ", "_").replace(":", "")}.ics'
    return response


@appoint_bp.route('/export_pdf_brief/<plan_id>', methods=['GET'])
def export_pdf_brief(plan_id):
    # 1. Daten holen (Hier als Beispiel, passe dies auf deine Datenbank an)
    # terminplan = Terminplan.query.get(plan_id)

    school_info = _get_school_info_for_export()

    school_name = school_info.get('name', 'Schulname')
    address = school_info.get('address', 'Adresse')
    postal_code = school_info.get('postal_code', 'PLZ')
    city = school_info.get('city', 'Stadt')
    school_number = school_info.get('school_number', '000000')
    it_admin = school_info.get('it_admin', 'IT-Beauftragter/in')
    tenant_id = _current_tenant_id()

    try:
        link = url_for('terminplaner.client', appointment_id=plan_id, tenant=tenant_id or None, _external=True)
    except Exception:
        host = _resolve_public_base_url()
        link = host + "/terminplaner/client/" + plan_id
        if tenant_id:
            link += f"?tenant={tenant_id}"

    schul_daten = {
        "schulname": school_name,
        "strasse": address,
        "plz_ort": f"{postal_code} {city}",
        "schulnummer": school_number,
        "it_admin": it_admin
    }
    
    plan_daten = {
        "titel": termin.get_item(plan_id).get('title', 'Terminplan'), # terminplan.title
        "link": link, # terminplan.link
        "notizen": termin.get_item(plan_id).get('note', '') # terminplan.note
    }

    # 2. QR-Code Bild im temporären Ordner erstellen
    qr = qrcode.QRCode(version=1, box_size=10, border=0)
    qr.add_data(plan_daten["link"])
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    fd, qr_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(qr_path)

    # 3. PDF im Speicher aufbauen (BytesIO)
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2.5*cm,
        topMargin=2.5*cm,
        bottomMargin=2*cm
    )
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Sender', fontSize=8, textColor=grey))
    styles.add(ParagraphStyle(name='Address', fontSize=10, leading=14))
    styles.add(ParagraphStyle(name='Date', fontSize=10, alignment=2))
    styles.add(ParagraphStyle(name='Subject', fontSize=14, fontName='Helvetica-Bold', spaceAfter=16, textColor=HexColor('#0f4c5c')))
    styles.add(ParagraphStyle(name='Body', fontSize=11, leading=16, spaceAfter=12))
    styles.add(ParagraphStyle(name='Notes', fontSize=10, leading=14, textColor=HexColor("#444444")))
    
    elements = []
    
    # Absenderzeile
    sender_text = f"<u>{schul_daten['schulname']} • {schul_daten['strasse']} • {schul_daten['plz_ort']}</u>"
    elements.append(Paragraph(sender_text, styles['Sender']))
    elements.append(Spacer(1, 1.5*cm))
    
    # Sichtfenster-Adresse (Generisch)
    elements.append(Paragraph("An die<br/>Teilnehmerinnen und Teilnehmer<br/>des Termins", styles['Address']))
    elements.append(Spacer(1, 2*cm))
    
    # Datum (Hier statisch zum Test, ggf. dynamisch per datetime)
    import datetime
    heute = datetime.datetime.now().strftime("%d.%m.%Y")
    elements.append(Paragraph(f"{schul_daten['stadt']}, den {heute}", styles['Date']))
    elements.append(Spacer(1, 1*cm))
    
    # Betreff
    elements.append(Paragraph(f"Einladung zur Terminbuchung: {plan_daten['titel']}", styles['Subject']))
    
    # Text
    elements.append(Paragraph("Sehr geehrte Damen und Herren,", styles['Body']))
    elements.append(Paragraph("hiermit möchten wir Sie herzlich einladen, einen Termin für unsere anstehende Veranstaltung zu buchen. Um den Prozess für alle Beteiligten so einfach und effizient wie möglich zu gestalten, nutzen wir unser Online-Buchungssystem.", styles['Body']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Link
    elements.append(Paragraph("<b>Ihr persönlicher Buchungslink:</b>", styles['Body']))
    link_html = f'<a href="{plan_daten["link"]}?" color="#16697a">{plan_daten["link"]}</a>'
    elements.append(Paragraph(link_html, styles['Body']))
    
    # Das vorhin erstellte QR-Code Bild einfügen
    elements.append(Spacer(1, 0.2*cm))
    elements.append(Image(qr_path, width=3*cm, height=3*cm, hAlign='LEFT'))
    elements.append(Spacer(1, 0.5*cm))
    
    # Notizen (falls vorhanden)
    if plan_daten.get('notizen'):
        elements.append(Paragraph("<b>Zusätzliche Informationen zum Termin:</b>", styles['Body']))
        elements.append(Paragraph(plan_daten['notizen'], styles['Notes']))
        
    elements.append(Spacer(1, 1.5*cm))
    
    # Grußformel
    elements.append(Paragraph("Mit freundlichen Grüßen,", styles['Body']))
    elements.append(Spacer(1, 1.5*cm))
    elements.append(Paragraph(f"<b>{schul_daten['schulname']}</b>", styles['Body']))
    
    # PDF fertigstellen
    doc.build(elements)
    
    # Temporäres Bild löschen
    if os.path.exists(qr_path):
        os.remove(qr_path)
    
    # Buffer auf Anfang zurücksetzen
    pdf_buffer.seek(0)
    
    # An Nutzer ausliefern
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Einladung_{plan_daten['titel'].replace(' ', '_')}.pdf"
    )

@appoint_bp.route('/')
def main():
    guard = _require_module_enabled()
    if guard:
        return guard

    current_user = session.get('username', '')
    upcoming_events = appointment_service.get_user_upcoming_events(current_user) if current_user else []
    tenant_id = _current_tenant_id()


    return render_template(
        'terminplaner.html',
        school_periods=cfg.SCHOOL_PERIODS,
        current_user=current_user,
        upcoming_events=upcoming_events,
        tenant_id=tenant_id,
    )