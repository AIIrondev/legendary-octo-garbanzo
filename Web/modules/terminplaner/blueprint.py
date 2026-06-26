from flask import Blueprint, render_template, request, session, url_for, redirect, flash
from flask import Response
import Web.modules.terminplaner.backend_server as appointment_service
import Web.modules.database.settings as cfg
import Web.modules.database.termine as termin
import Web.modules.database.user as us

# Create a blueprint instance
appoint_bp = Blueprint('terminplaner', __name__)


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

@appoint_bp.route('/client/<appointment_id>', methods=['POST', 'GET'])
def client(appointment_id):
    """
    The Route for the terminplaner to work with the client
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
    
    # Extract the custom fields defined by the appointment owner
    custom_fields = appointment_item.get('custom_fields', [])

    can_view_booking_names = False
    if current_user:
        try:
            can_view_booking_names = bool(us.check_admin(current_user) or current_user == appointment_owner)
        except Exception:
            can_view_booking_names = bool(current_user == appointment_owner)

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
        start_daytime = request.form.get('start_day_time')
        username = request.form.get('client_name')
        
        custom_answers = request.form.getlist('custom_answers')

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

        flash('Der Termin konnte nicht gespeichert werden.', 'error')

    return render_template(
        'termin_client.html',
        appointment_id=appointment_id,
        available=available_for_view,
        current_user=session.get('username', ''),
        tenant_id=_current_tenant_id(),
        can_view_booking_names=can_view_booking_names,
        custom_fields=custom_fields
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
    Route for authenticated persons to configure a new appointment for them
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

        if not start or not end or not time or not slots_amount or not slot_length or not title:
            flash('Bitte alle Pflichtfelder ausfüllen.', 'error')
            return render_template(
                'termin_configure.html',
                school_periods=cfg.SCHOOL_PERIODS,
                generated_link=None,
                email_service_enabled=cfg.EMAIL_ENABLED,
            )

        # Variablen im Funktionsaufruf aktualisiert
        result = appointment_service.new(start, end, time, slots_amount, slot_length, session["username"], mail, note, calendar_enabled=add_to_calendar, title=title, custom_fields=custom)
        flash('Der Terminplan wurde angelegt.', 'success')
        return render_template(
            'termin_configure.html',
            school_periods=cfg.SCHOOL_PERIODS,
            generated_link=result['link'],
            calendar_link=result.get('calendar_link'),
            add_to_calendar=add_to_calendar,
            email_service_enabled=cfg.EMAIL_ENABLED,
            title=title,
        )
    elif request.method == "GET":
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