"""
Class for all funktions of the executive -> Lehrer
"""
import datetime
from datetime import timedelta
from flask import url_for
import Web.modules.emailservice.email as mail_service
import Web.modules.database.termine as termin
import Web.modules.database.settings as cfg
from Web.tenant import get_tenant_context


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
    try:
        link = url_for('terminplaner.client', appointment_id=str(appointment_id), _external=True)
    except Exception:
        tenant_context = get_tenant_context()
        subdomain = ''
        if tenant_context:
            subdomain = getattr(tenant_context, 'subdomain', '') or getattr(tenant_context, 'tenant_id', '') or ''
        host = f"https://{subdomain}.invario.eu" if subdomain else "https://invario.eu"
        link = host + "/terminplaner/client/" + str(appointment_id)

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
        'END:VEVENT',
        'END:VCALENDAR',
        '',
    ]
    return '\r\n'.join(ics_lines)


def new(date_start: str, date_end: str, time_span: list, slots: int, slot_lenght: int, user: str, mail: list=[], note:str="", calendar_enabled: bool=False) -> dict:
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
    id = termin.add(date_start, date_end, normalized_time_span, slots, slot_lenght, user, normalized_mail, note, calendar_enabled=calendar_enabled)
    id_str = str(id)

    tenant_context = get_tenant_context()
    subdomain = ''
    if tenant_context:
        subdomain = getattr(tenant_context, 'subdomain', '') or getattr(tenant_context, 'tenant_id', '') or ''

    try:
        link = url_for('terminplaner.client', appointment_id=id_str, _external=True)
    except Exception:
        host = f"https://{subdomain}.invario.eu" if subdomain else "https://invario.eu"
        link = host + "/terminplaner/client/" + id_str
    subject = f"Terminanfrage von {user}"
    note_link = note + f"Bitte klicken sie auf den folgenden Link um einen Termin zu vereinbaren: {link}"
    calendar_link = None
    if calendar_enabled:
        try:
            calendar_link = url_for('terminplaner.calendar_export', appointment_id=id_str, _external=True)
        except Exception:
            tenant_context = get_tenant_context()
            subdomain = ''
            if tenant_context:
                subdomain = getattr(tenant_context, 'subdomain', '') or getattr(tenant_context, 'tenant_id', '') or ''
            host = f"https://{subdomain}.invario.eu" if subdomain else "https://invario.eu"
            calendar_link = host + "/terminplaner/calendar/" + id_str + ".ics"

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
        slots_left = max(0, total_slots - slots_used)

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