import logging
import re
from transformers import pipeline, AutoTokenizer
import torch

logger = logging.getLogger(__name__)

class EmailSummarizer:
    """Email summarizer using facebook/bart-large-cnn"""
    
    def __init__(self):
        self.model_name = "facebook/bart-large-cnn"
        self.max_length = 1024
        self.min_length = 50
        self.device = -1  # CPU only
        
        try:
            logger.info(f"Loading summarization model: {self.model_name}")
            # Load tokenizer for token-length estimation
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.summarizer = pipeline(
                "summarization",
                model=self.model_name,
                device=self.device
            )
            logger.info("Summarization model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load summarization model: {e}")
            raise
    
    def summarize_email(self, email_data):
        """Summarize an email"""
        try:
            # Extract email content
            subject = email_data.get('subject', '')
            body = email_data.get('body', '')
            from_email = email_data.get('from', '')
            
            # Clean and prepare text
            email_text = self._prepare_email_text(subject, body, from_email)
            
            # Check if text is too long and needs chunking
            if len(email_text) > 4000:  # BART's effective limit
                email_text = self._chunk_and_summarize(email_text)
            else:
                email_text = self._summarize_text(email_text)
            
            # Format the summary
            summary = self._format_summary(email_text, from_email, subject)
            
            logger.info("Email summarized successfully")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to summarize email: {e}")
            # Return a fallback summary
            return self._create_fallback_summary(email_data)
    
    def _prepare_email_text(self, subject, body, from_email):
        """Prepare email text for summarization"""
        # Clean HTML tags if present
        body = self._clean_html(body)
        
        # Remove excessive whitespace
        body = re.sub(r'\s+', ' ', body).strip()
        
        # Combine subject and body
        if subject:
            email_text = f"Subject: {subject}\n\n{body}"
        else:
            email_text = body
        
        return email_text
    
    def _clean_html(self, text):
        """Remove HTML tags from text"""
        # Simple HTML tag removal
        text = re.sub(r'<[^>]+>', '', text)
        # Decode common HTML entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        return text
    
    def _chunk_and_summarize(self, text):
        """Chunk long text and summarize each chunk"""
        try:
            # Split text into chunks
            chunks = self._split_text_into_chunks(text, 3000)
            
            summaries = []
            for chunk in chunks:
                chunk_summary = self._summarize_text(chunk)
                summaries.append(chunk_summary)
            
            # Combine chunk summaries
            combined_summary = " ".join(summaries)
            
            # If still too long, summarize again
            if len(combined_summary) > 2000:
                combined_summary = self._summarize_text(combined_summary)
            
            return combined_summary
            
        except Exception as e:
            logger.error(f"Error in chunk summarization: {e}")
            # Fallback: return first part of text
            return text[:1000] + "..."
    
    def _split_text_into_chunks(self, text, chunk_size):
        """Split text into chunks of specified size"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_length = len(word)
            else:
                current_chunk.append(word)
                current_length += len(word) + 1
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _summarize_text(self, text):
        """Summarize text using BART model"""
        try:
            # Ensure text is not empty
            if not text.strip():
                return "No content to summarize."
            
            # Truncate if too long (BART has token limits)
            if len(text) > 4000:
                text = text[:4000]
            
            # Estimate token length and set safe bounds dynamically
            try:
                token_count = len(self.tokenizer.encode(text, add_special_tokens=False))
            except Exception:
                token_count = max(1, len(text.split()))

            # Derive dynamic lengths to avoid HF IndexError on short inputs
            dyn_min = max(10, min(60, int(token_count * 0.2)))
            dyn_max = max(dyn_min + 10, min(180, int(token_count * 0.6)))

            # If very short input, skip model and return trimmed text
            if token_count < 20:
                sentences = text.split('. ')
                return ('. '.join(sentences[:2]) + '.').strip()

            # Generate summary with dynamic parameters and robust fallbacks
            try:
                result = self.summarizer(
                    text,
                    max_length=dyn_max,
                    min_length=dyn_min,
                    do_sample=False,
                    early_stopping=True,
                    num_beams=4,
                    truncation=True
                )
            except IndexError:
                # Retry with smaller bounds
                dyn_min = max(5, int(dyn_min * 0.6))
                dyn_max = max(dyn_min + 10, int(dyn_max * 0.8))
                try:
                    result = self.summarizer(
                        text,
                        max_length=dyn_max,
                        min_length=dyn_min,
                        do_sample=False,
                        early_stopping=True,
                        num_beams=2,
                        truncation=True
                    )
                except Exception:
                    # Final attempt: remove min_length constraint entirely
                    try:
                        result = self.summarizer(
                            text,
                            max_length=max(30, min(120, dyn_max)),
                            do_sample=False,
                            early_stopping=True,
                            num_beams=2,
                            truncation=True
                        )
                    except Exception:
                        # Give up and return heuristic fallback
                        sentences = text.split('. ')
                        return ('. '.join(sentences[:3]) + '.').strip()
            
            if isinstance(result, list) and len(result) > 0 and 'summary_text' in result[0]:
                return result[0]['summary_text']
            if isinstance(result, dict) and 'summary_text' in result:
                return result['summary_text']
            return "Unable to generate summary."
                
        except Exception as e:
            logger.error(f"Error in text summarization: {e}")
            # Fallback: return first few sentences
            sentences = text.split('. ')
            return '. '.join(sentences[:3]) + '.'
    
    def _format_summary(self, summary, from_email, subject):
        """Format the summary for WhatsApp"""
        # Extract sender name from email
        sender_name = self._extract_sender_name(from_email)
        
        formatted_summary = f"From: {sender_name}\n"
        if subject:
            formatted_summary += f"Subject: {subject}\n"
        formatted_summary += f"\nSummary:\n{summary}"
        
        return formatted_summary
    
    def _extract_sender_name(self, from_email):
        """Extract sender name from email address"""
        if not from_email:
            return "Unknown Sender"
        
        # Try to extract name from "Name <email@domain.com>" format
        match = re.match(r'^(.+?)\s*<(.+)>$', from_email)
        if match:
            name = match.group(1).strip().strip('"')
            return name if name else match.group(2)
        
        # If no name, return email address
        return from_email
    
    def _create_fallback_summary(self, email_data):
        """Create a fallback summary when summarization fails"""
        subject = email_data.get('subject', 'No Subject')
        from_email = email_data.get('from', 'Unknown Sender')
        snippet = email_data.get('snippet', '')
        
        sender_name = self._extract_sender_name(from_email)
        
        fallback = f"From: {sender_name}\n"
        fallback += f"Subject: {subject}\n"
        fallback += f"\nSnippet: {snippet[:200]}..."
        
        return fallback
    
    def get_model_info(self):
        """Get information about the loaded model"""
        return {
            'model_name': self.model_name,
            'max_length': self.max_length,
            'min_length': self.min_length,
            'device': 'CPU' if self.device == -1 else f'GPU {self.device}'
        }
