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
        slot_minutes = int(item.get('slot_length') or item.get('slot_lenght') or 0)
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


def new(date_start: str, date_end: str, time_span: list, slots, slot_length, user: str, mail: list=None, note:str="", calendar_enabled: bool=False, title: str="", custom_fields: list = (), clients_per_slot: int=1) -> dict:
    """
    Generates a link for the executive to send to his clients to book a time Slot
    """
    try:
        slots_int = int(slots)
    except (ValueError, TypeError):
        slots_int = 0
        
    try:
        custom_fields.pop(-1)
    except :
        pass

    try:
        slot_length_int = int(slot_length)
    except (ValueError, TypeError):
        slot_length_int = 45

    normalized_time_span = _normalize_time_span(time_span)
    normalized_mail = _normalize_mail_list(mail or [])
    
    id = termin.add(date_start, date_end, normalized_time_span, slots_int, slot_length_int, user, normalized_mail, note, calendar_enabled=calendar_enabled, title=title, custom_fields=custom_fields, clients_p_slot=clients_per_slot)
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
    
        
def book_slot(id, date_start_time, name, custom: tuple = ()):
    try:
        item = termin.get_item(id)
        if not item:
            return False

        slots = item.get('slots_booked', []) or []
        if not isinstance(slots, list):
            slots = []

        # 1. Check overall total booking capacity 
        capacity = int(item.get('slots', 0) or 0)
        if capacity and len(slots) >= capacity:
            return False

        # 2. Prevent the exact same user from double-booking the exact same slot
        for existing in slots:
            if isinstance(existing, (list, tuple)) and len(existing) >= 2:
                if existing[0] == date_start_time and existing[1] == name:
                    return False

        # 3. Check concurrent capacity for this specific time slot
        clients_per_slot = int(item.get('clients_per_slot', 1) or 1)
        bookings_at_time = sum(
            1 for existing in slots 
            if isinstance(existing, (list, tuple)) and len(existing) > 0 and existing[0] == date_start_time
        )
        
        if bookings_at_time >= clients_per_slot:
            return False

        # Append the new booking successfully
        slots.append((date_start_time, name, custom))
        success = termin.update(id, slots)
        return bool(success)
        
    except Exception as e:
        print(f"Error booking slot: {e}")
        return False


def remove_slot(id, date_start_time, name):
    try:
        if hasattr(termin, 'remove_slot'):
            removed = termin.remove_slot(id, date_start_time, name)
            if removed:
                return True

        item = termin.get_item(id)
        if not item:
            return False

        slots = item.get('slots_booked', []) or []
        new_slots = []
        for s in slots:
            try:
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
    try:
        return bool(termin.remove(id))
    except Exception as e:
        print(f"Error removing appointment: {e}")
        return False

def get_available(id):
    try:
        termin_range = termin.get_item(id)
        if not termin_range:
            return {}

        date_start = termin_range.get('date_start')
        date_end = termin_range.get('date_end')
        time_span = termin_range.get('time_span', [])
        
        # Safe integer parsing without heavy try-except blocks
        try:
            total_slots = int(termin_range.get('slots', 0) or 0)
        except (ValueError, TypeError):
            total_slots = 0

        # Support both spellings gracefully
        raw_length = termin_range.get('slot_length') or termin_range.get('slot_lenght') or 0
        try:
            slot_length = int(raw_length)
        except (ValueError, TypeError):
            slot_length = raw_length

        clients_per_slot = int(termin_range.get('clients_per_slot', 1) or 1)
        booked = termin_range.get('slots_booked', []) or []

        # Normalize the bookings list safely
        normalized = []
        bookings_by_time = {}  # Tracks how many people are in each specific time slot
        
        for s in booked:
            if isinstance(s, (list, tuple)) and len(s) >= 2:
                slot_time = s[0]
                item = {'start': slot_time, 'name': s[1]}
            elif isinstance(s, dict):
                slot_time = s.get('start')
                item = s
            else:
                slot_time = str(s)
                item = {'value': s}
                
            normalized.append(item)
            
            # Count concurrent bookings per timestamp
            if slot_time:
                bookings_by_time[slot_time] = bookings_by_time.get(slot_time, 0) + 1

        # Calculate remaining total capacity safely
        slots_used = len(normalized)
        slots_left = max(0, total_slots - slots_used)

        return {
            'date_start': date_start,
            'date_end': date_end,
            'time_span': time_span,
            'slot_length': slot_length,
            'slot_lenght': slot_length,
            'slots_total': total_slots,
            'clients_per_slot': clients_per_slot,
            'slots_booked': normalized,
            'slots_left': slots_left,
            'bookings_by_time': bookings_by_time
        }
    except Exception as e:
        print(f"Error getting available slots: {e}")
        return {}

def get_available_user(id):
    return get_available(id)


def get_user_upcoming_events(user: str, limit: int = 25) -> list[dict]:
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
                'custom_fields': list(item.get('custom_fields')),
            }
        )

    return result