# communications/management/commands/sync_emails.py
from django.core.management.base import BaseCommand
from core.utils.email_receiver import fetch_unread_emails
import time

class Command(BaseCommand):
    help = 'Sincroniza los correos entrantes usando IMAP'

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando monitor de correos...")
        try:
            while True:
                fetch_unread_emails()
                # === ¡CAMBIO AQUÍ! ===
                print(".", end="", flush=True)
                time.sleep(15) # Revisa cada 15 segundos
        except KeyboardInterrupt:
            self.stdout.write("\nMonitor detenido.")