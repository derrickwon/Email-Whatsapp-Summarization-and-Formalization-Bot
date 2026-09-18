import logging
import os
import json
import re
from transformers import pipeline, AutoTokenizer
import torch

logger = logging.getLogger(__name__)

class ReplyFormalizer:
    """Reply formalizer using google/flan-t5-large"""
    
    def __init__(self):
        self.model_name = "google/flan-t5-large"
        self.device = -1  # CPU only
        self.max_length = 512
        self.user_name = os.getenv('MY_NAME', '[Your Name]')
        
        try:
            logger.info(f"Loading formalization model: {self.model_name}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.formalizer = pipeline(
                "text2text-generation",
                model=self.model_name,
                device=self.device,
                max_length=self.max_length,
                do_sample=True,
                temperature=0.7
            )
            logger.info("Formalization model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load formalization model: {e}")
            raise
    
    def formalize_reply(self, original_email, informal_reply, edit_instruction=None):
        """Formalize an informal reply into a professional email"""
        try:
            # Create the prompt for formalization
            prompt = self._create_formalization_prompt(original_email, informal_reply, edit_instruction)
            
            # Generate formalized content
            result = self.formalizer(prompt, max_length=400, do_sample=True, temperature=0.7)
            
            if result and len(result) > 0:
                generated_text = result[0]['generated_text']
                
                # Parse the generated text to extract subject and body
                formalized_data = self._parse_formalized_output(generated_text)
                
                # If parsing fails, try alternative approach
                if not formalized_data:
                    formalized_data = self._fallback_formalization(informal_reply, original_email)
                else:
                    # Ensure the closing signature uses the configured user name
                    formalized_data = self._ensure_signature_name(formalized_data)
                    formalized_data = self._ensure_opening_and_closing(
                        formalized_data,
                        informal_reply
                    )
                
                logger.info("Reply formalized successfully")
                return formalized_data
                
            else:
                logger.warning("No formalized text generated, using fallback")
                return self._fallback_formalization(informal_reply, original_email)
                
        except Exception as e:
            logger.error(f"Failed to formalize reply: {e}")
            return self._fallback_formalization(informal_reply, original_email)
    
    def _create_formalization_prompt(self, original_email, informal_reply, edit_instruction=None):
        """Create a prompt for formalization"""
        subject = original_email.get('subject', '')
        from_email = original_email.get('from', '')
        
        # Extract sender name
        sender_name = self._extract_sender_name(from_email)
        
        prompt = f"""Convert this informal WhatsApp message into a professional email reply.

Original email subject: {subject}
Original sender: {sender_name}
Informal reply: {informal_reply}"""

        if edit_instruction:
            prompt += f"\nEdit instruction: {edit_instruction}"
        
        prompt += """

Please format the response as JSON with the following structure:
{
    "subject": "Re: [original subject]",
    "body": "Professional email body with proper greeting, content, and closing"
}

Requirements:
- Use professional tone
- Include proper greeting (Dear [Name],)
- Include proper closing exactly as: Best regards, {self.user_name}
- Keep the core message from the informal reply
- Make it appropriate for business communication
- If edit instruction is provided, incorporate those changes

JSON response:"""
        
        return prompt
    
    def _parse_formalized_output(self, generated_text):
        """Parse the generated text to extract JSON"""
        try:
            # Try to find JSON in the generated text
            json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
                parsed_data = json.loads(json_str)
                
                # Validate required fields
                if 'subject' in parsed_data and 'body' in parsed_data:
                    return {
                        'subject': parsed_data['subject'].strip(),
                        'body': parsed_data['body'].strip()
                    }
            
            # If JSON parsing fails, try to extract subject and body manually
            return self._extract_subject_and_body(generated_text)
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed: {e}")
            return self._extract_subject_and_body(generated_text)
        except Exception as e:
            logger.error(f"Error parsing formalized output: {e}")
            return None
    
    def _extract_subject_and_body(self, text):
        """Extract subject and body from non-JSON text"""
        try:
            lines = text.strip().split('\n')
            subject = ""
            body_lines = []
            in_body = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for subject indicators
                if line.lower().startswith('subject:') or line.lower().startswith('re:'):
                    subject = line.replace('Subject:', '').replace('subject:', '').strip()
                    if not subject.startswith('Re:'):
                        subject = f"Re: {subject}"
                    in_body = True
                elif in_body:
                    body_lines.append(line)
            
            # If no subject found, create one
            if not subject:
                subject = "Re: Email Reply"
            
            # Join body lines
            body = '\n'.join(body_lines).strip()
            
            if body:
                return {
                    'subject': subject,
                    'body': body
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting subject and body: {e}")
            return None
    
    def _fallback_formalization(self, informal_reply, original_email):
        """Create a fallback formalized reply when AI fails"""
        subject = original_email.get('subject', 'Email Reply')
        from_email = original_email.get('from', '')
        
        # Extract sender name
        sender_name = self._extract_sender_name(from_email)
        
        # Create a basic formal structure
        subject_line = f"Re: {subject}" if not subject.startswith('Re:') else subject
        
        # Clean up the informal reply
        cleaned_reply = self._clean_informal_text(informal_reply)
        
        # Create formal body
        body = f"""Dear {sender_name},

{cleaned_reply}

Best regards,
{self.user_name}"""
        
        draft = {
            'subject': subject_line,
            'body': body
        }
        draft = self._ensure_signature_name(draft)
        return self._ensure_opening_and_closing(draft, informal_reply)

    def _ensure_signature_name(self, draft):
        """Ensure the draft body ends with the configured user name, replacing placeholders if needed."""
        body = draft.get('body', '')
        placeholders = ["[Your Name]", "Your Name", "[your name]", "[NAME]", "[name]"]
        for ph in placeholders:
            if ph in body:
                body = body.replace(ph, self.user_name)
        # If no placeholder but body ends with generic closing, append name if missing
        if body.strip().lower().endswith('best regards,'):
            body = body + "\n" + self.user_name
        draft['body'] = body
        return draft

    def _ensure_opening_and_closing(self, draft, informal_reply):
        """Guarantee an opening line tailored to the reply and a closing line before the sign off."""
        body = draft.get('body', '').strip()
        if not body:
            return draft

        opening_line = self._generate_opening_line(informal_reply)
        closing_line = self._generate_closing_line(informal_reply)

        if opening_line:
            body = self._insert_opening_line(body, opening_line)
        if closing_line:
            body = self._insert_closing_line(body, closing_line)

        draft['body'] = body.strip()
        return draft

    def _insert_opening_line(self, body, opening_line):
        """Insert the opening line immediately after the greeting if present."""
        normalized = body.lower()
        if opening_line.lower() in normalized:
            return body

        greeting_match = re.match(r'^(Dear[^\n]*\n*)', body, re.IGNORECASE)
        if greeting_match:
            start = greeting_match.end()
            prefix = body[:start].rstrip()
            remainder = body[start:].lstrip('\n')
            return f"{prefix}\n\n{opening_line}\n\n{remainder}"

        return f"{opening_line}\n\n{body}"

    def _insert_closing_line(self, body, closing_line):
        """Insert the closing line immediately before the signature/sign off."""
        normalized = body.lower()
        if closing_line.lower() in normalized:
            return body

        closing_pattern = re.compile(r'(Best regards,.*)', re.IGNORECASE | re.DOTALL)
        match = closing_pattern.search(body)
        if match:
            before = body[:match.start()].rstrip()
            closing_block = match.group(1).lstrip()
            return f"{before}\n\n{closing_line}\n\n{closing_block}"

        return f"{body.rstrip()}\n\n{closing_line}\n\nBest regards,\n{self.user_name}"

    def _generate_opening_line(self, informal_reply):
        """Create an empathetic opening sentence based on the informal reply."""
        cleaned = self._clean_informal_text(informal_reply or '').strip()
        if not cleaned:
            return "Thank you for your message."

        first_sentence = re.split(r'(?<=[.!?])\s+', cleaned)[0].strip()
        first_sentence = self._shorten_text(first_sentence, 160)
        if not first_sentence.endswith(('.', '!', '?')):
            first_sentence += '.'

        if first_sentence.lower().startswith('thank you'):
            return first_sentence

        return f"Thank you for reaching out. {first_sentence}"

    def _generate_closing_line(self, informal_reply):
        """Create a closing sentence that reflects the intent of the reply."""
        text = (informal_reply or '').lower()

        if any(keyword in text for keyword in ['question', 'clarify', 'clarification']):
            return "Please let me know if you need any additional clarification."
        if any(keyword in text for keyword in ['schedule', 'meeting', 'call', 'availability']):
            return "I look forward to coordinating the schedule together."
        if any(keyword in text for keyword in ['thanks', 'thank you', 'appreciate']):
            return "I appreciate your collaboration and support."
        if any(keyword in text for keyword in ['deliverable', 'timeline', 'deadline', 'update']):
            return "I will keep you updated on the next steps."

        return "Please let me know if you need any further assistance."

    def _shorten_text(self, text, limit):
        """Trim text to a soft character limit without breaking words."""
        text = text.strip()
        if len(text) <= limit:
            return text
        trimmed = text[:limit].rsplit(' ', 1)[0]
        return trimmed.strip()
    
    def _clean_informal_text(self, text):
        """Clean informal text for professional use"""
        # Remove common WhatsApp/informal elements
        text = re.sub(r'\b(ok|okay|k|kk)\b', 'understood', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(yeah|yep|yup)\b', 'yes', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(nah|nope)\b', 'no', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(thx|thanks)\b', 'thank you', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(pls|please)\b', 'please', text, flags=re.IGNORECASE)
        
        # Remove excessive punctuation
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        
        return text
    
    def _extract_sender_name(self, from_email):
        """Extract sender name from email address"""
        if not from_email:
            return "Sir/Madam"
        
        # Try to extract name from "Name <email@domain.com>" format
        match = re.match(r'^(.+?)\s*<(.+)>$', from_email)
        if match:
            name = match.group(1).strip().strip('"')
            return name if name else "Sir/Madam"
        
        # Extract name from email address
        email_part = from_email.split('@')[0]
        # Replace dots and underscores with spaces
        name = email_part.replace('.', ' ').replace('_', ' ')
        # Capitalize words
        name = ' '.join(word.capitalize() for word in name.split())
        
        return name if name else "Sir/Madam"
    
    def apply_edit_instruction(self, current_draft, edit_instruction):
        """Apply edit instruction to current draft"""
        try:
            prompt = f"""Modify this email draft based on the edit instruction.

Current draft:
Subject: {current_draft['subject']}
Body: {current_draft['body']}

Edit instruction: {edit_instruction}

Please provide the updated email as JSON:
{{
    "subject": "Updated subject",
    "body": "Updated body"
}}

JSON response:"""
            
            result = self.formalizer(prompt, max_length=400, do_sample=True, temperature=0.7)
            
            if result and len(result) > 0:
                generated_text = result[0]['generated_text']
                updated_data = self._parse_formalized_output(generated_text)
                
                if updated_data:
                    return updated_data
            
            # Fallback: simple text replacement
            return self._simple_edit_fallback(current_draft, edit_instruction)
            
        except Exception as e:
            logger.error(f"Failed to apply edit instruction: {e}")
            return self._simple_edit_fallback(current_draft, edit_instruction)
    
    def _simple_edit_fallback(self, current_draft, edit_instruction):
        """Simple fallback for edit instructions"""
        # Basic keyword-based editing
        body = current_draft['body']
        
        if 'tone' in edit_instruction.lower():
            if 'formal' in edit_instruction.lower():
                body = body.replace('Hi', 'Dear').replace('Hey', 'Dear')
            elif 'casual' in edit_instruction.lower():
                body = body.replace('Dear', 'Hi')
        
        if 'shorter' in edit_instruction.lower():
            # Remove some sentences
            sentences = body.split('. ')
            if len(sentences) > 2:
                body = '. '.join(sentences[:2]) + '.'
        
        return {
            'subject': current_draft['subject'],
            'body': body
        }
    
    def get_model_info(self):
        """Get information about the loaded model"""
        return {
            'model_name': self.model_name,
            'max_length': self.max_length,
            'device': 'CPU' if self.device == -1 else f'GPU {self.device}'
        }
