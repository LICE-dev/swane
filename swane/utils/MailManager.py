import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class MailManager:
    """
    Mail Sending service manager
    """

    TIMEOUT = 2

    def __init__(self, server_address: str, server_port: int, username: str, password: str, use_ssl: bool= True, use_tls: bool=False):
        """
        The MailManager initializer.
        
        Parameters
        ----------
        server_address : str
            The mail host server address
        server_port : int
            The mail host server port
        username : str
            The email
        password : str
            The email password
        use_ssl : bool. Optional
            True to use the SSL protocol, otherwhise False. The default is True
        use_tls : bool. Optional
            True to use the TLS protocol, otherwhise False. Useless if use_ssl is True. The default is False
            
        """
        
        self.server_address = server_address
        self.server_port = server_port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.use_tls = use_tls
        self.server = None

    def connect(self):
        """
        Connects to the SMTP server using the provided credentials.

        """

        try:
            if self.use_ssl:
                self.server = smtplib.SMTP_SSL(self.server_address, self.server_port, timeout=MailManager.TIMEOUT)
            else:
                self.server = smtplib.SMTP(self.server_address, self.server_port, timeout=MailManager.TIMEOUT)
                self.server.ehlo()
                if self.use_tls:
                    self.server.starttls()
                    self.server.ehlo()
            self.server.login(self.username, self.password)
        except Exception as e:
            raise Exception(f"{str(e)} - Check your Mail Configuration")

    def disconnect(self):
        """
        Disconnects from the SMTP server.

        """

        if self.server:
            self.server.quit()

    def send_mail(self, from_addr, to_addr, subject, body):
        """
        Sends an email with the specified subject and body.

        """

        try:
            message = MIMEMultipart()
            message["From"] = from_addr
            message["To"] = to_addr
            message["Subject"] = subject
            message.attach(MIMEText(body, "html"))

            self.connect()
            self.server.send_message(message)
            self.disconnect()
        except Exception as e:
            raise

    def send_report(self, body):
        """
        Sends a report for a SWANe workflow based on the user mail configuration
        """

        self.send_mail(self.username, self.username, f"SWANe - {datetime.now()}", body)
