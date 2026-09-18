import os
import logging
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

logger = logging.getLogger(__name__)

class WhatsAppService:
    """Twilio WhatsApp service wrapper"""
    
    def __init__(self):
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
        self.my_whatsapp_number = os.getenv('MY_WHATSAPP_NUMBER')
        
        if not all([self.account_sid, self.auth_token, self.whatsapp_number, self.my_whatsapp_number]):
            raise ValueError("Missing required Twilio environment variables")
        
        self.client = Client(self.account_sid, self.auth_token)
        logger.info("WhatsApp service initialized successfully")
    
    def send_message(self, message_body):
        """Send a WhatsApp message"""
        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.whatsapp_number,
                to=self.my_whatsapp_number
            )
            
            logger.info(f"WhatsApp message sent successfully: {message.sid}")
            return message.sid
            
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            raise
    
    def send_message_to_number(self, message_body, to_number):
        """Send a WhatsApp message to a specific number"""
        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.whatsapp_number,
                to=to_number
            )
            
            logger.info(f"WhatsApp message sent to {to_number}: {message.sid}")
            return message.sid
            
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message to {to_number}: {e}")
            raise
    
    def create_response(self, message_body):
        """Create a TwiML response for webhook"""
        response = MessagingResponse()
        response.message(message_body)
        return str(response)
    
    def validate_webhook_request(self, request):
        """Validate incoming webhook request from Twilio"""
        try:
            # Basic validation - in production, you should validate the signature
            required_fields = ['Body', 'From', 'MessageSid']
            
            for field in required_fields:
                if field not in request.form:
                    logger.warning(f"Missing required field in webhook: {field}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating webhook request: {e}")
            return False
    
    def get_message_status(self, message_sid):
        """Get the status of a sent message"""
        try:
            message = self.client.messages(message_sid).fetch()
            return {
                'sid': message.sid,
                'status': message.status,
                'error_code': message.error_code,
                'error_message': message.error_message
            }
            
        except Exception as e:
            logger.error(f"Error getting message status: {e}")
            return None
    
    def format_message_for_whatsapp(self, content, message_type="text"):
        """Format content for WhatsApp display"""
        if message_type == "email_summary":
            return f"📧 Email Summary:\n\n{content}\n\nPlease reply with your informal response."
        
        elif message_type == "draft_confirmation":
            return f"📝 Draft Ready:\n\n{content}\n\nReply 'CONFIRM' to send or 'EDIT [instructions]' to modify."
        
        elif message_type == "success":
            return f"✅ {content}"
        
        elif message_type == "error":
            return f"❌ {content}"
        
        else:
            return content
    
    def send_email_summary(self, summary):
        """Send email summary to WhatsApp"""
        formatted_message = self.format_message_for_whatsapp(summary, "email_summary")
        return self.send_message(formatted_message)
    
    def send_draft_confirmation(self, subject, body):
        """Send draft for confirmation"""
        content = f"Subject: {subject}\n\nBody:\n{body}"
        formatted_message = self.format_message_for_whatsapp(content, "draft_confirmation")
        return self.send_message(formatted_message)
    
    def send_success_message(self, message):
        """Send success message"""
        formatted_message = self.format_message_for_whatsapp(message, "success")
        return self.send_message(formatted_message)
    
    def send_error_message(self, message):
        """Send error message"""
        formatted_message = self.format_message_for_whatsapp(message, "error")
        return self.send_message(formatted_message)
