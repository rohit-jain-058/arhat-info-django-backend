from django.core.mail import EmailMessage
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def send_proposal_email(
    to_email:      str,
    proposal_text: str,
    pdf_bytes:     bytes,
    project_data:  dict,
) -> bool:
    """
    Send proposal email with PDF attached.
    Returns True if sent successfully.
    """
    project_type = project_data.get("project_type", "Project").replace("_", " ").title()
    cost         = project_data.get("cost", {})
    timeline     = project_data.get("timeline", "?")

    subject = f"Your Project Proposal — {project_type} | Tylented"

    body = f"""Hi,

Thank you for discussing your project with us. Please find your full project proposal attached.

Project Summary:
- Type: {project_type}
- Timeline: {timeline} weeks
- Investment: ${cost.get('min', 0):,} – ${cost.get('max', 0):,} USD

{proposal_text[:500]}...

The full proposal is attached as a PDF.

Next steps:
1. Review the attached proposal
2. Book a 30-min call: https://calendly.com/arhatinfo
3. Reply to this email with any questions

Looking forward to working with you.

Best regards,
Rohit Jain
Tylented Engineering
hello@arhatinfo.com
arhatinfo.com
"""

    try:
        email = EmailMessage(
            subject    = subject,
            body       = body,
            from_email = settings.DEFAULT_FROM_EMAIL,
            to         = [to_email],
            cc         = [settings.TEAM_EMAIL],
        )
        email.attach(
            filename     = "tylented-proposal.pdf",
            content      = pdf_bytes,
            mimetype     = "application/pdf",
        )
        email.send(fail_silently=False)
        logger.info(f"Proposal email sent to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False