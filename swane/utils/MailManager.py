import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class MailManager:
    """
    Manager mail sending
    """
    
    def __init__(self, server_address, server_port, username, password, use_tls=True):
        self.server_address = server_address
        self.server_port = server_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.server = None
        self.use_ssl = True

    def connect(self):
        """
        Connect to the SMTP server using the provided credentials.
        """
        try:
            if self.use_ssl:
                self.server = smtplib.SMTP_SSL(self.server_address, self.server_port)
            else:
                self.server = smtplib.SMTP(self.server_address, self.server_port)
                self.server.ehlo()
                if self.use_tls:
                    self.server.starttls()
                    self.server.ehlo()
            self.server.login(self.username, self.password)
        except Exception as e:
            print(f"Error connecting to the server: {e}")
            raise

    def disconnect(self):
        """
        Disconnect from the SMTP server.
        """
        if self.server:
            self.server.quit()

    def send_mail(self, from_addr, to_addr, subject, body):
        """
        Send an email with the specified subject and body.
        """
        
        message = MIMEMultipart()
        message['From'] = from_addr
        message['To'] = to_addr
        message['Subject'] = subject
        message.attach(MIMEText(body, 'html'))

        self.connect()
        
        self.server.send_message(message)
        
        self.disconnect()

    def send_report(self, body):
        """
        Send a report for a SWANe workflow based on the user mail configuration
        """
        
        self.send_mail(self.username, self.username, f"SWANe - {datetime.now()}", body)