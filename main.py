import os
import time
import threading
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import json

from gmail_service import GmailService
from whatsapp_service import WhatsAppService
from summarizer_local import EmailSummarizer
from formalizer_local import ReplyFormalizer

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize services
gmail_service = None
whatsapp_service = None
summarizer = None
formalizer = None

# Global state for managing email workflow
pending_replies = {}  # {message_id: {'original_email': email_data, 'draft': draft_data}}
# Short ID mappings for user-friendly referencing
short_id_to_email_id = {}
email_id_to_short_id = {}

def _generate_short_id(email_id: str) -> str:
    """Generate a short human-friendly ID from the Gmail message id."""
    # Take last 6 chars for brevity; ensure uppercase alnum only
    short = email_id[-6:].upper()
    return short

def initialize_services():
    """Initialize all required services"""
    global gmail_service, whatsapp_service, summarizer, formalizer
    
    try:
        gmail_service = GmailService()
        whatsapp_service = WhatsAppService()
        summarizer = EmailSummarizer()
        formalizer = ReplyFormalizer()
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

def _send_whatsapp_summary(email):
    """Summarize and send a single email to WhatsApp, registering short ID."""
    email_id = email['id']
    summary = summarizer.summarize_email(email)
    short_id = _generate_short_id(email_id)
    short_id_to_email_id[short_id] = email_id
    email_id_to_short_id[email_id] = short_id
    whatsapp_service.send_message(
        "📧 New Email Summary [ID: " + short_id + "]:\n\n" +
        summary +
        "\n\nInstructions:\n" +
        "- R " + short_id + " <your reply>  → set your reply for this email\n" +
        "- EDIT " + short_id + " <instructions>  → modify the draft\n" +
        "- CONFIRM " + short_id + "  → send the current draft"
    )
    pending_replies[email_id] = {
        'original_email': email,
        'summary': summary,
        'status': 'waiting_for_reply',
        'timestamp': time.time()
    }

def fetch_and_send_unread(limit=10):
    """On-demand fetch: get newest unread emails and send summaries."""
    try:
        unread_emails = gmail_service.get_unread_emails(max_results=limit)
        # sort newest first by internal date if available
        unread_emails.sort(key=lambda e: int(e.get('internal_date', 0)), reverse=True)
        for email in unread_emails:
            email_id = email['id']
            if email_id in pending_replies:
                continue
            _send_whatsapp_summary(email)
    except Exception as e:
        logger.error(f"Failed on on-demand fetch: {e}")

def _resolve_target_email_id_from_message(message_body: str):
    """Try to extract a target email id from message by short id token."""
    tokens = message_body.strip().split()
    if not tokens:
        return None
    cmd = tokens[0].upper()
    short_id = None
    # Commands that may include an explicit short id as the second token
    if cmd in {"CONFIRM", "EDIT", "R"} and len(tokens) >= 2:
        candidate = tokens[1].upper()
        if candidate in short_id_to_email_id:
            return short_id_to_email_id[candidate]
    return None

def _get_latest_pending_email_id():
    latest_email_id = None
    latest_timestamp = 0
    for email_id, data in pending_replies.items():
        if data.get('status') in {'waiting_for_reply', 'waiting_for_confirmation'}:
            ts = data.get('timestamp', 0)
            if ts > latest_timestamp:
                latest_timestamp = ts
                latest_email_id = email_id
    return latest_email_id

def _append_edit_to_draft_body(body: str, addition: str) -> str:
    """Append the edit text to the draft body, placing it before the signature if present."""
    addition = addition.strip()
    if not addition:
        return body
    
    body = body.rstrip()
    closing_pattern = re.compile(r'(Best regards,\s*\n.*)', re.IGNORECASE | re.DOTALL)
    closing_match = closing_pattern.search(body)
    
    if closing_match:
        main_content = body[:closing_match.start()].rstrip()
        closing = closing_match.group(1).lstrip('\n')
        updated = main_content
        if updated:
            updated += "\n\n"
        updated += addition
        updated += "\n\n" + closing
        return updated
    
    if body:
        return body + "\n\n" + addition
    
    return addition


def process_whatsapp_reply(message_body, sender_number):
    """Process incoming WhatsApp message"""
    logger.info(f"Processing WhatsApp message from {sender_number}: {message_body}")
    
    # Determine target email id (from explicit short id or fallback to latest)
    target_email_id = _resolve_target_email_id_from_message(message_body)
    if not target_email_id:
        target_email_id = _get_latest_pending_email_id()

    if not target_email_id:
        whatsapp_service.send_message("No pending email replies found. Please check if there are new emails.")
        return
    
    data = pending_replies[target_email_id]
    short_id = email_id_to_short_id.get(target_email_id, "?")
    
    tokens = message_body.strip().split()
    upper_msg = message_body.strip().upper()

    if upper_msg.startswith("CONFIRM"):
        # Send the formalized draft as email reply
        try:
            if 'formalized_draft' not in data:
                whatsapp_service.send_message("No draft available to confirm. Please provide a reply first.")
                return
            
            draft = data['formalized_draft']
            gmail_service.send_reply(
                target_email_id,
                draft['subject'],
                draft['body']
            )
            
            # Clean up
            del pending_replies[target_email_id]
            # Clean id mappings
            if short_id in short_id_to_email_id:
                del short_id_to_email_id[short_id]
            if target_email_id in email_id_to_short_id:
                del email_id_to_short_id[target_email_id]
            
            whatsapp_service.send_message("✅ Email reply sent successfully for ID: " + short_id)
            logger.info(f"Email reply sent for {target_email_id}")
            
        except Exception as e:
            logger.error(f"Failed to send email reply: {e}")
            whatsapp_service.send_message(f"❌ Failed to send email reply: {str(e)}")
    
    elif upper_msg.startswith("EDIT"):
        # Append the user-provided text directly to the existing draft
        try:
            # If message like: EDIT <ID> <instructions>
            parts = message_body.strip().split(maxsplit=2)
            if len(parts) >= 3 and parts[1].upper() in short_id_to_email_id:
                addition_text = parts[2].strip()
            else:
                # Fallback: everything after 'EDIT '
                addition_text = message_body.strip()[5:].strip()
            
            if not addition_text:
                whatsapp_service.send_message("Please include the text you want to add to the draft.")
                return
            
            if 'formalized_draft' not in data:
                whatsapp_service.send_message("No draft available to edit. Please create a draft first by sending a reply.")
                return
            
            current_draft = data['formalized_draft']
            updated_body = _append_edit_to_draft_body(current_draft.get('body', ''), addition_text)
            current_draft['body'] = updated_body
            
            data['formalized_draft'] = current_draft
            data['status'] = 'waiting_for_confirmation'
            
            # Send updated draft for confirmation
            whatsapp_service.send_message(
                f"📝 Updated Draft [ID: {short_id}]:\n\n"
                f"Subject: {current_draft['subject']}\n\n"
                f"Body:\n{current_draft['body']}\n\n"
                f"Reply 'CONFIRM {short_id}' to send or 'EDIT {short_id} [instructions]' to modify further."
            )
            
            logger.info(f"Draft updated for {target_email_id}")
            
        except Exception as e:
            logger.error(f"Failed to update draft: {e}")
            whatsapp_service.send_message(f"❌ Failed to update draft: {str(e)}")
    
    else:
        # This is an informal reply - support explicit R <ID> <message>
        try:
            if upper_msg.startswith('R '):
                parts = message_body.strip().split(maxsplit=2)
                if len(parts) >= 3 and parts[1].upper() in short_id_to_email_id:
                    informal_reply = parts[2].strip()
                else:
                    # No valid short id provided; treat remainder as reply
                    informal_reply = message_body.strip()[2:].strip()
            else:
                informal_reply = message_body.strip()
            
            # Formalize the reply
            formalized_draft = formalizer.formalize_reply(
                data['original_email'],
                informal_reply
            )
            
            data['informal_reply'] = informal_reply
            data['formalized_draft'] = formalized_draft
            data['status'] = 'waiting_for_confirmation'
            
            # Send formalized draft for confirmation
            whatsapp_service.send_message(
                f"📝 Formalized Draft [ID: {short_id}]:\n\n"
                f"Subject: {formalized_draft['subject']}\n\n"
                f"Body:\n{formalized_draft['body']}\n\n"
                f"Reply 'CONFIRM {short_id}' to send or 'EDIT {short_id} [instructions]' to modify further."
            )
            
            logger.info(f"Reply formalized for {target_email_id}")
            
        except Exception as e:
            logger.error(f"Failed to formalize reply: {e}")
            whatsapp_service.send_message(f"❌ Failed to formalize reply: {str(e)}")

@app.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Twilio webhook endpoint for incoming WhatsApp messages"""
    try:
        message_body = request.form.get('Body', '')
        sender_number = request.form.get('From', '')
        
        logger.info(f"Received WhatsApp message: {message_body} from {sender_number}")
        
        # Keyword activation: SEND EMAILS or FETCH EMAILS will push newest unread
        if message_body.strip().upper().startswith(('SEND EMAILS', 'FETCH EMAILS', 'EMAILS', 'FETCH')):
            # optional limit parsing: e.g., FETCH 5
            parts = message_body.strip().split()
            limit = 1
            if len(parts) >= 2 and parts[1].isdigit():
                limit = int(parts[1])
            fetch_and_send_unread(limit=limit)
            return jsonify({'status': 'triggered'})

        # Process the message
        process_whatsapp_reply(message_body, sender_number)
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'pending_replies': len(pending_replies)
    })

@app.route('/status', methods=['GET'])
def status():
    """Status endpoint showing current state"""
    return jsonify({
        'pending_replies': {
            email_id: {
                'status': data['status'],
                'summary': data.get('summary', '')[:100] + '...' if data.get('summary') else '',
                'timestamp': data.get('timestamp', 0)
            }
            for email_id, data in pending_replies.items()
        }
    })

if __name__ == '__main__':
    try:
        # Initialize services
        initialize_services()
        
        logger.info("Flask app starting (keyword-activated fetch)...")
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
