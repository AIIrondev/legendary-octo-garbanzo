"""
Class for all funktions of the executive -> Lehrer
"""
import datetime
import emailservice.email as mail_service
import Web.modules.database.termine as termin
import Web.modules.database.settings as cfg
from tenant import get_tenant_context

def new(date_start: str, date_end: str, time_span: list, slots: int, slot_lenght: int, user: str, mail: list=[], note:str="") -> str:
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
    id = termin.add(date_start, date_end, time_span, slots, slot_lenght, user, mail, note)

    tenant_context = get_tenant_context()
    subdomain = ''
    if tenant_context:
        subdomain = getattr(tenant_context, 'subdomain', '') or getattr(tenant_context, 'tenant_id', '') or ''

    host = f"https://{subdomain}.invario.eu" if subdomain else "invario.eu"
    link = host + "/terminplaner/client" + "?" + "client_id=" + id 
    subject = f"Terminanfrage von {user}"
    note_link = note + f"Bitte klicken sie auf den folgenden Link um einen Termin zu vereinbaren: {link}"
    mail_service.send(mail, subject, note_link)
    return link
    
        
def book_slot(id, date, start_time):
    """
    
    """
    termin.update()