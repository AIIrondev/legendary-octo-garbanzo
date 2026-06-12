from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from modules.module_registry import ModuleRegistry as mr
import smtplib

import Web.modules.database.settings as cfg


def _build_smtp_client():
    smtp = smtplib.SMTP(cfg.EMAIL_SMTP_HOST, cfg.EMAIL_SMTP_PORT, timeout=cfg.EMAIL_TIMEOUT_SECONDS)
    smtp.ehlo()
    if cfg.EMAIL_USE_TLS:
        smtp.starttls()
        smtp.ehlo()
    if cfg.EMAIL_USERNAME:
        smtp.login(cfg.EMAIL_USERNAME, cfg.EMAIL_PASSWORD or '')
    return smtp

def send(email: list, subject: str, note: str, sender: str) -> bool:
  """
  Sends the email with the link to the Clients

  Input:
  - email: Email list of all the addresses to send the link to ["","",""]
  - subject: Subject of the email
  - note: Note that is send with the Emails

  Output:
  - bool: true if the sending worked and false if it didnt
  """
  if not mr.registry.is_enabled('mail'):
    return False
  else:
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sender or cfg.EMAIL_FROM_ADDRESS or cfg.EMAIL_USERNAME
    msg['To'] = ', '.join(email) if isinstance(email, (list, tuple)) else str(email)
    msg.attach(MIMEText(note))
    smtp = None
    try:
      smtp = _build_smtp_client()
      smtp.sendmail(from_addr=msg['From'], to_addrs=email, msg=msg.as_string())
      return True
    except Exception:
      return False
    finally:
      try:
        if smtp:
          smtp.quit()
      except Exception:
        pass