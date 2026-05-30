from flask import Blueprint, render_template, request, session, url_for, redirect, flash
from flask import Response
import Web.modules.terminplaner.backend_server as appointment_service
import Web.modules.database.settings as cfg

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

    if request.method == 'POST':
        start_daytime = request.form.get('start_day_time')
        username = request.form.get('client_name')
        if not start_daytime or not username:
            flash('Bitte Name und gewünschte Uhrzeit angeben.', 'error')
            return render_template(
                'termin_client.html',
                appointment_id=appointment_id,
                available=available,
                current_user=session.get('username', ''),
            )

        if appointment_service.book_slot(appointment_id, start_daytime, username):
            flash('Der Termin wurde gespeichert.', 'success')
            return redirect(url_for('terminplaner.client', appointment_id=appointment_id))

        flash('Der Termin konnte nicht gespeichert werden.', 'error')

    return render_template(
        'termin_client.html',
        appointment_id=appointment_id,
        available=available,
        current_user=session.get('username', ''),
    )

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
        slot_lenght = request.form.get('slot_lenght')
        mail = request.form.get('mail', '')
        note = request.form.get('note', '')
        add_to_calendar = request.form.get('add_to_calendar') == 'on'

        if not start or not end or not time or not slots_amount or not slot_lenght:
            flash('Bitte alle Pflichtfelder ausfüllen.', 'error')
            return render_template(
                'termin_configure.html',
                school_periods=cfg.SCHOOL_PERIODS,
                generated_link=None,
                email_service_enabled=cfg.EMAIL_ENABLED,
            )

        result = appointment_service.new(start, end, time, slots_amount, slot_lenght, session["username"], mail, note, calendar_enabled=add_to_calendar)
        flash('Der Terminplan wurde angelegt.', 'success')
        return render_template(
            'termin_configure.html',
            school_periods=cfg.SCHOOL_PERIODS,
            generated_link=result['link'],
            calendar_link=result.get('calendar_link'),
            add_to_calendar=add_to_calendar,
            email_service_enabled=cfg.EMAIL_ENABLED,
        )
    elif request.method == "GET":
        return render_template(
            'termin_configure.html',
            school_periods=cfg.SCHOOL_PERIODS,
            generated_link=None,
            calendar_link=None,
            add_to_calendar=False,
            email_service_enabled=cfg.EMAIL_ENABLED,
        )


@appoint_bp.route('/calendar/<appointment_id>.ics', methods=['GET'])
def calendar_export(appointment_id):
    guard = _require_module_enabled()
    if guard:
        return guard

    ics_content = appointment_service.build_calendar_ics(appointment_id)
    if not ics_content:
        return _appointment_not_found_response()

    response = Response(ics_content, mimetype='text/calendar; charset=utf-8')
    response.headers['Content-Disposition'] = f'attachment; filename=terminplan-{appointment_id}.ics'
    return response

@appoint_bp.route('/')
def main():
    guard = _require_module_enabled()
    if guard:
        return guard

    return render_template(
        'terminplaner.html',
        school_periods=cfg.SCHOOL_PERIODS,
        current_user=session.get('username', ''),
    )