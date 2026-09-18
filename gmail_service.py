import os
import base64
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

class GmailService:
    """Gmail API service wrapper"""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
              'https://www.googleapis.com/auth/gmail.modify',
              'https://www.googleapis.com/auth/gmail.send']
    
    def __init__(self):
        self.service = None
        self.credentials = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API using OAuth2"""
        try:
            # Check if token.json exists
            if os.path.exists('token.json'):
                self.credentials = Credentials.from_authorized_user_file('token.json', self.SCOPES)
            
            # If there are no valid credentials, get new ones
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    # Check if credentials.json exists
                    if not os.path.exists('credentials.json'):
                        raise FileNotFoundError(
                            "credentials.json not found. Please download it from Google Cloud Console "
                            "and place it in the project root."
                        )
                    
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
                    self.credentials = flow.run_local_server(port=0)
                
                # Save credentials for next run
                with open('token.json', 'w') as token:
                    token.write(self.credentials.to_json())
            
            # Build the Gmail service
            self.service = build('gmail', 'v1', credentials=self.credentials)
            logger.info("Gmail authentication successful")
            
        except Exception as e:
            logger.error(f"Gmail authentication failed: {e}")
            raise
    
    def get_unread_emails(self, max_results=10):
        """Get list of unread emails"""
        try:
            # Query for unread emails
            results = self.service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for message in messages:
                email_data = self._get_email_details(message['id'])
                if email_data:
                    emails.append(email_data)
            
            logger.info(f"Retrieved {len(emails)} unread emails")
            return emails
            
        except HttpError as error:
            logger.error(f"Error retrieving emails: {error}")
            return []
    
    def _get_email_details(self, message_id):
        """Get detailed information about a specific email"""
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload'].get('headers', [])
            
            # Extract email details
            email_data = {
                'id': message_id,
                'thread_id': message.get('threadId'),
                'snippet': message.get('snippet', ''),
                'subject': '',
                'from': '',
                'to': '',
                'date': '',
                'body': '',
                'internal_date': int(message.get('internalDate', '0'))
            }
            
            # Parse headers
            for header in headers:
                name = header['name'].lower()
                value = header['value']
                
                if name == 'subject':
                    email_data['subject'] = value
                elif name == 'from':
                    email_data['from'] = value
                elif name == 'to':
                    email_data['to'] = value
                elif name == 'date':
                    email_data['date'] = value
            
            # Extract email body
            email_data['body'] = self._extract_email_body(message['payload'])
            
            return email_data
            
        except HttpError as error:
            logger.error(f"Error getting email details for {message_id}: {error}")
            return None
    
    def _extract_email_body(self, payload):
        """Extract email body from payload"""
        body = ""
        
        if 'parts' in payload:
            # Multipart message
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
                elif part['mimeType'] == 'text/html' and not body:
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        else:
            # Single part message
            if payload['mimeType'] == 'text/plain':
                if 'data' in payload['body']:
                    body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
            elif payload['mimeType'] == 'text/html':
                if 'data' in payload['body']:
                    body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body
    
    def mark_as_read(self, message_id):
        """Mark an email as read"""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"Marked email {message_id} as read")
            
        except HttpError as error:
            logger.error(f"Error marking email as read: {error}")
    
    def send_reply(self, original_message_id, subject, body):
        """Send a reply to an email"""
        try:
            # Get the original message to extract thread ID and recipient
            original_message = self.service.users().messages().get(
                userId='me',
                id=original_message_id,
                format='full'
            ).execute()
            
            headers = original_message['payload'].get('headers', [])
            thread_id = original_message.get('threadId')
            
            # Extract recipient (original sender)
            recipient = ""
            for header in headers:
                if header['name'].lower() == 'from':
                    recipient = header['value']
                    break
            
            # Create the reply message
            message = MIMEText(body)
            message['to'] = recipient
            message['subject'] = subject
            
            # Encode the message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Send the reply
            reply_message = self.service.users().messages().send(
                userId='me',
                body={
                    'raw': raw_message,
                    'threadId': thread_id
                }
            ).execute()
            
            logger.info(f"Reply sent successfully: {reply_message['id']}")
            return reply_message['id']
            
        except HttpError as error:
            logger.error(f"Error sending reply: {error}")
            raise
    
    def get_email_thread(self, thread_id):
        """Get all messages in a thread"""
        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id
            ).execute()
            
            return thread.get('messages', [])
            
        except HttpError as error:
            logger.error(f"Error getting thread: {error}")
            return []
