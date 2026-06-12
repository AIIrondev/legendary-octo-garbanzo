"""
Class for all funktions of the executive -> Lehrer
"""
import datetime
from datetime import timedelta
from flask import url_for, has_request_context, request
import Web.modules.emailservice.email as mail_service
import Web.modules.database.termine as termin
import Web.modules.database.settings as cfg
from Web.tenant import get_tenant_context


def _resolve_public_base_url() -> str:
    if has_request_context():
        try:
            return request.url_root.rstrip('/')
        except Exception:
            pass

    tenant_context = get_tenant_context()
    subdomain = ''
    if tenant_context:
        subdomain = getattr(tenant_context, 'subdomain', '') or getattr(tenant_context, 'tenant_id', '') or ''
    return f"https://{subdomain}.invario.eu" if subdomain else "https://invario.eu"


def _current_tenant_id() -> str:
    tenant_context = get_tenant_context()
    if tenant_context and getattr(tenant_context, 'tenant_id', None):
        return str(tenant_context.tenant_id)
    if has_request_context():
        try:
            return str(request.args.get('tenant', '') or request.args.get('tenant_id', '') or '').strip()
        except Exception:
            return ''
    return ''


def _normalize_time_span(time_span):
    if isinstance(time_span, list):
        return [str(entry).strip() for entry in time_span if str(entry).strip()]
    if isinstance(time_span, tuple):
        return [str(entry).strip() for entry in time_span if str(entry).strip()]
    if isinstance(time_span, str):
        normalized = []
        for line in time_span.replace(';', '\n').replace(',', '\n').splitlines():
            value = line.strip()
            if value:
                normalized.append(value)
        return normalized
    return []


def _normalize_mail_list(mail):
    if isinstance(mail, list):
        return [str(entry).strip() for entry in mail if str(entry).strip()]
    if isinstance(mail, tuple):
        return [str(entry).strip() for entry in mail if str(entry).strip()]
    if isinstance(mail, str):
        return [entry.strip() for entry in mail.replace(';', ',').split(',') if entry.strip()]
    return []

def _escape_ics_text(value):
    return str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r\n', '\n').replace('\n', '\\n').replace('\r', '')


def _format_ics_date(date_value):
    if isinstance(date_value, datetime.datetime):
        return date_value.strftime('%Y%m%dT%H%M%SZ')
    if isinstance(date_value, datetime.date):
        return date_value.strftime('%Y%m%d')
    return ''


def build_calendar_ics(appointment_id: str) -> str | None:
    item = termin.get_item(appointment_id)
    if not item:
        return None

    date_start = item.get('date_start')
    date_end = item.get('date_end')
    time_span = item.get('time_span', []) or []
    creator = item.get('user', 'Terminplaner')
    note = item.get('note', '') or ''
    titel = item.get('title', '') or ''
    tenant_id = _current_tenant_id()
    try:
        link = url_for('terminplaner.client', appointment_id=str(appointment_id), tenant=tenant_id or None, _external=True)
    except Exception:
        host = _resolve_public_base_url()
        link = host + "/terminplaner/client/" + str(appointment_id)
        if tenant_id:
            link += f"?tenant={tenant_id}"

    try:
        start_date = datetime.datetime.strptime(str(date_start), '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(str(date_end), '%Y-%m-%d').date()
    except Exception:
        return None

    uid = f"terminplaner-{appointment_id}@invario.eu"
    created_at = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    summary = f"Terminplan für {creator}"
    description_lines = [
        f"Buchungslink: {link}",
        f"Zeitraum: {date_start} bis {date_end}",
    ]
    if time_span:
        description_lines.append('Zeitfenster: ' + '; '.join(str(entry) for entry in time_span))
    if note:
        description_lines.append('Notiz: ' + str(note))
    if titel:
        description_lines.append('Titel: ' + str(titel))

    ics_lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Inventarsystem//Terminplaner//DE',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        f'UID:{uid}',
        f'DTSTAMP:{created_at}',
        f'SUMMARY:{_escape_ics_text(summary)}',
        f'DESCRIPTION:{_escape_ics_text(chr(10).join(description_lines))}',
        f'URL:{_escape_ics_text(link)}',
        f'DTSTART;VALUE=DATE:{_format_ics_date(start_date)}',
        f'DTEND;VALUE=DATE:{_format_ics_date(end_date + timedelta(days=1))}',
        f'Titel:{_escape_ics_text(titel)}',
        'END:VEVENT',
        'END:VCALENDAR',
        '',
    ]
    return '\r\n'.join(ics_lines)


def build_client_slot_ics(appointment_id: str, slot_start: str, client_name: str = '') -> str | None:
    """Build a single-slot ICS export for a client booking candidate."""
    item = termin.get_item(appointment_id)
    if not item:
        return None

    try:
        start_dt = datetime.datetime.strptime(str(slot_start).strip(), '%Y-%m-%d %H:%M')
    except Exception:
        return None

    try:
        slot_minutes = int(item.get('slot_lenght') or 0)
    except Exception:
        slot_minutes = 0
    if slot_minutes <= 0:
        slot_minutes = 45

    end_dt = start_dt + datetime.timedelta(minutes=slot_minutes)
    tenant_id = _current_tenant_id()

    try:
        link = url_for('terminplaner.client', appointment_id=str(appointment_id), tenant=tenant_id or None, _external=True)
    except Exception:
        host = _resolve_public_base_url()
        link = host + '/terminplaner/client/' + str(appointment_id)
        if tenant_id:
            link += f'?tenant={tenant_id}'

    title_name = item.get('title') or f"Terminbuchung mit {client_name}" if client_name else "Terminbuchung"
    summary = f"{title_name} - Terminbuchung"
    description_lines = [
        f"Buchungslink: {link}",
        f"Geplanter Termin: {start_dt.strftime('%d.%m.%Y %H:%M')} - {end_dt.strftime('%H:%M')}",
    ]

    uid = f"terminplaner-slot-{appointment_id}-{start_dt.strftime('%Y%m%d%H%M')}@invario.eu"
    created_at = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    dt_start = start_dt.strftime('%Y%m%dT%H%M%S')
    dt_end = end_dt.strftime('%Y%m%dT%H%M%S')

    ics_lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Inventarsystem//Terminplaner Client Slot//DE',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        f'UID:{uid}',
        f'DTSTAMP:{created_at}',
        f'SUMMARY:{_escape_ics_text(summary)}',
        f'DESCRIPTION:{_escape_ics_text(chr(10).join(description_lines))}',
        f'URL:{_escape_ics_text(link)}',
        f'DTSTART:{dt_start}',
        f'DTEND:{dt_end}',
        f'Titel:{_escape_ics_text(summary)}',
        'END:VEVENT',
        'END:VCALENDAR',
        '',
    ]
    return '\r\n'.join(ics_lines)


def new(date_start: str, date_end: str, time_span: list, slots: int, slot_lenght: int, user: str, mail: list=[], note:str="", calendar_enabled: bool=False, title: str="") -> dict:
    """
    Generates a link for the executive to send to his clients to book a time Slot
    
    Input:
    - date_start: start of the time frae area
    - date_end: end of the time frame area
    - time_span: Time window for the days as a list [(first day Time Frame), (second day Time frame), (third etc.)]
    - slots: amount of slots that are available
    - slot_lenght: the lenght of a slot in minutes

    Output:
    - link: The link for the user to send to the clients
    """
    normalized_time_span = _normalize_time_span(time_span)
    normalized_mail = _normalize_mail_list(mail)
    id = termin.add(date_start, date_end, normalized_time_span, slots, slot_lenght, user, normalized_mail, note, calendar_enabled=calendar_enabled, title=title)
    id_str = str(id)
    tenant_id = _current_tenant_id()

    try:
        link = url_for('terminplaner.client', appointment_id=id_str, tenant=tenant_id or None, _external=True)
    except Exception:
        host = _resolve_public_base_url()
        link = host + "/terminplaner/client/" + id_str
        if tenant_id:
            link += f"?tenant={tenant_id}"
    subject = f"{title} - Bitte Termin vereinbaren" if title else f"Terminanfrage von {user} - Bitte Termin vereinbaren"
    note_link = note + f"Bitte klicken sie auf den folgenden Link um einen Termin zu vereinbaren: {link}"
    calendar_link = None
    if calendar_enabled:
        try:
            calendar_link = url_for('terminplaner.calendar_export', appointment_id=id_str, tenant=tenant_id or None, _external=True)
        except Exception:
            host = _resolve_public_base_url()
            calendar_link = host + "/terminplaner/calendar/" + id_str + ".ics"
            if tenant_id:
                calendar_link += f"?tenant={tenant_id}"

    email_body = note_link
    if calendar_link:
        email_body += f"\n\nKalendereintrag: {calendar_link}"

    if normalized_mail and cfg.EMAIL_ENABLED:
        mail_service.send(normalized_mail, subject, email_body)

    return {
        'appointment_id': id_str,
        'link': link,
        'calendar_link': calendar_link,
    }
    
        
def book_slot(id, date_start_time, name):
    """
    Updates slot for the booking per a id

    Input:
    - id: the id is the id you get from the
    - date_start_time: the date of the booking that was selected with date and time
    - name: name that the client gave himself
    
    Output:
    - bool: if worked or not
    """
    try:
        # Retrieve the current appointment
        item = termin.get_item(id)
        if not item:
            return False

        slots = item.get('slots_booked', []) or []
        if not isinstance(slots, list):
            slots = []

        capacity = int(item.get('slots', 0) or 0)
        if capacity and len(slots) >= capacity:
            return False

        for existing in slots:
            if isinstance(existing, (list, tuple)) and len(existing) >= 2:
                if existing[0] == date_start_time and existing[1] == name:
                    return False

        # Append the new booking as a tuple (start_time, name)
        slots.append((date_start_time, name))

        # Update the appointment in the database
        success = termin.update(id, slots)
        return bool(success)
    except Exception as e:
        print(f"Error booking slot: {e}")
        return False


def remove_slot(id, date_start_time, name):
    """
    Remove a booked slot for an appointment.

    Returns True if the removal succeeded, False otherwise.
    """
    try:
        # Prefer DB-level remove if available
        if hasattr(termin, 'remove_slot'):
            removed = termin.remove_slot(id, date_start_time, name)
            if removed:
                return True

        # Fallback: fetch, filter, and replace the slot list
        item = termin.get_item(id)
        if not item:
            return False

        slots = item.get('slots_booked', []) or []
        new_slots = []
        for s in slots:
            try:
                # s may be list or tuple like [start_time, name]
                if isinstance(s, (list, tuple)) and len(s) >= 2 and s[0] == date_start_time and s[1] == name:
                    continue
            except Exception:
                pass
            new_slots.append(s)

        success = termin.update(id, new_slots)
        return bool(success)
    except Exception as e:
        print(f"Error removing slot: {e}")
        return False


def remove_appointment(id):
    """
    Remove an entire appointment by id.
    """
    try:
        return bool(termin.remove(id))
    except Exception as e:
        print(f"Error removing appointment: {e}")
        return False

def get_available(id):
    """
    Gets the available time slots -> more over it returns the time frame and the allready booked slots also the lenght.
    And checks if there are slots left.

    Input:
    - id: id of the appointment

    Output:
    - dict: all the needet information -> [Start_date, End_date, (first day Time Frame, 
    second day Time frame, third etc.), slot lenght, (bookedslots -> list)]
    """
    try:
        termin_range = termin.get_item(id)
        if not termin_range:
            return {}

        date_start = termin_range.get('date_start')
        date_end = termin_range.get('date_end')
        time_span = termin_range.get('time_span', [])
        slot_lenght = termin_range.get('slot_lenght')
        total_slots = termin_range.get('slots', 0)
        # Ensure numeric fields are cast to int when stored as strings
        try:
            total_slots = int(termin_range.get('slots', 0) or 0)
        except Exception:
            total_slots = 0

        try:
            slot_lenght = int(termin_range.get('slot_lenght') or 0)
        except Exception:
            slot_lenght = termin_range.get('slot_lenght')

        booked = termin_range.get('slots_booked', []) or []

        # Normalize booked entries to dicts for easier consumption
        normalized = []
        for s in booked:
            if isinstance(s, (list, tuple)) and len(s) >= 2:
                normalized.append({'start': s[0], 'name': s[1]})
            elif isinstance(s, dict):
                normalized.append(s)
            else:
                normalized.append({'value': s})

        slots_used = len(normalized)
        try:
            slots_left = max(0, int(total_slots) - slots_used)
        except Exception:
            slots_left = max(0, slots_used - slots_used)

        return {
            'date_start': date_start,
            'date_end': date_end,
            'time_span': time_span,
            'slot_lenght': slot_lenght,
            'slots_total': total_slots,
            'slots_booked': normalized,
            'slots_left': slots_left,
        }
    except Exception as e:
        print(f"Error getting available slots: {e}")
        return {}

def get_available_user(id):
    """
    Gets the available time slots -> more over it returns the time frame and the allready booked slots also the lenght.
    And checks if there are slots left.

    Input:
    - id: id of the appointment

    Output:
    - dict: all the needet information -> [Start_date, End_date, (first day Time Frame, 
    second day Time frame, third etc.), slot lenght, (bookedslots -> list)]
    """
    return get_available(id)


def get_user_upcoming_events(user: str, limit: int = 25) -> list[dict]:
    """Return upcoming appointment plans for overview display."""
    user_name = str(user or '').strip()
    if not user_name:
        return []

    appointments = termin.get_upcoming_for_user(user_name, limit=limit)
    host = _resolve_public_base_url()
    tenant_id = _current_tenant_id()

    result = []
    for item in appointments:
        appointment_id = str(item.get('_id') or '')
        if not appointment_id:
            continue

        try:
            link = url_for('terminplaner.client', appointment_id=appointment_id, tenant=tenant_id or None, _external=True)
        except Exception:
            link = host + '/terminplaner/client/' + appointment_id
            if tenant_id:
                link += f'?tenant={tenant_id}'

        try:
            calendar_link = url_for('terminplaner.calendar_export', appointment_id=appointment_id, tenant=tenant_id or None, _external=True)
        except Exception:
            calendar_link = host + '/terminplaner/calendar/' + appointment_id + '.ics'
            if tenant_id:
                calendar_link += f'?tenant={tenant_id}'

        slots_total = int(item.get('slots', 0) or 0)
        slots_booked = item.get('slots_booked', []) or []
        if not isinstance(slots_booked, list):
            slots_booked = []

        result.append(
            {
                'appointment_id': appointment_id,
                'date_start': str(item.get('date_start') or ''),
                'date_end': str(item.get('date_end') or ''),
                'time_span': item.get('time_span', []) or [],
                'slots_total': slots_total,
                'slots_booked': len(slots_booked),
                'slots_left': max(0, slots_total - len(slots_booked)),
                'note': str(item.get('note') or ''),
                'link': link,
                'calendar_link': calendar_link if item.get('calendar_enabled') else None,
                'title': str(item.get('title') or ''),
            }
        )

    return result