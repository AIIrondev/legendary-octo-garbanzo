from flask import Blueprint, render_template, request, session, url_for, redirect, flash
import Web.modules.terminplaner.backend_server as appointment_service
import Web.modules.database.settings as cfg

# Create a blueprint instance
appoint_bp = Blueprint('terminplaner', __name__)


def _require_module_enabled():
    if not cfg.MODULES.is_enabled('terminplan'):
        flash('Der Terminplaner ist deaktiviert.', 'info')
        return redirect(url_for('home'))
    return None

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
        flash('Der Termin wurde nicht gefunden.', 'error')
        return redirect(url_for('terminplan'))

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

        if not start or not end or not time or not slots_amount or not slot_lenght:
            flash('Bitte alle Pflichtfelder ausfüllen.', 'error')
            return render_template(
                'termin_configure.html',
                school_periods=cfg.SCHOOL_PERIODS,
                generated_link=None,
                email_service_enabled=cfg.EMAIL_ENABLED,
            )

        link = appointment_service.new(start, end, time, slots_amount, slot_lenght, session["username"], mail, note)
        flash('Der Terminplan wurde angelegt.', 'success')
        return render_template(
            'termin_configure.html',
            school_periods=cfg.SCHOOL_PERIODS,
            generated_link=link,
            email_service_enabled=cfg.EMAIL_ENABLED,
        )
    elif request.method == "GET":
        return render_template(
            'termin_configure.html',
            school_periods=cfg.SCHOOL_PERIODS,
            generated_link=None,
            email_service_enabled=cfg.EMAIL_ENABLED,
        )

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