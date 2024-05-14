import smtplib
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

    def connect(self):
        """
        Connect to the SMTP server using the provided credentials.
        """
        self.server = smtplib.SMTP(self.server_address, self.server_port)
        if self.use_tls:
            self.server.starttls()
        self.server.login(self.username, self.password)

    def send_mail(self, from_addr, to_addr, subject, body):
        """
        Send an email with the specified subject and body.
        """
        message = MIMEMultipart()
        message['From'] = from_addr
        message['To'] = to_addr
        message['Subject'] = subject
        message.attach(MIMEText(body, 'plain'))
        
        self.server.send_message(message)

    def disconnect(self):
        """
        Disconnect from the SMTP server.
        """
        if self.server:
            self.server.quit()