from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.lib import colors
import io


DARK    = HexColor("#001B26")
BLUE    = HexColor("#35BBEA")
WHITE   = HexColor("#FFFFFF")
GREY    = HexColor("#4A5568")


def generate_proposal_pdf(proposal_text: str, project_data: dict) -> bytes:
    """
    Generate a PDF from the proposal text.
    Returns bytes — save to file or attach to email.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize    = A4,
        rightMargin = 2*cm,
        leftMargin  = 2*cm,
        topMargin   = 2*cm,
        bottomMargin= 2*cm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "Title",
        parent    = styles["Heading1"],
        fontSize  = 24,
        textColor = DARK,
        spaceAfter= 6,
        fontName  = "Helvetica-Bold",
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent    = styles["Heading2"],
        fontSize  = 14,
        textColor = BLUE,
        spaceBefore=12,
        spaceAfter = 4,
        fontName  = "Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "Body",
        parent    = styles["Normal"],
        fontSize  = 10,
        textColor = DARK,
        spaceAfter= 6,
        leading   = 16,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent    = styles["Normal"],
        fontSize  = 9,
        textColor = GREY,
        spaceAfter= 4,
    )

    story = []

    # ── Header ────────────────────────────────────────────────────────
    story.append(Paragraph("Arhatinfo Engineering", title_style))
    story.append(Paragraph("Project Proposal", heading_style))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE))
    story.append(Spacer(1, 0.4*cm))

    # Meta info
    from datetime import date
    story.append(Paragraph(f"Date: {date.today().strftime('%B %d, %Y')}", meta_style))
    if project_data.get("complexity"):
        story.append(Paragraph(f"Complexity: {project_data['complexity'].title()}", meta_style))
    if project_data.get("timeline"):
        story.append(Paragraph(f"Timeline: {project_data['timeline']} weeks", meta_style))
    if project_data.get("cost"):
        cost = project_data["cost"]
        story.append(Paragraph(
            f"Investment: ${cost.get('min',0):,} – ${cost.get('max',0):,} USD",
            meta_style,
        ))
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Spacer(1, 0.3*cm))

    # ── Proposal body — parse markdown-ish headings ───────────────────
    for line in proposal_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.2*cm))
        elif line.startswith("# "):
            story.append(Paragraph(line[2:], title_style))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], heading_style))
        elif line.startswith("### "):
            story.append(Paragraph(f"<b>{line[4:]}</b>", body_style))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph(f"• {line[2:]}", body_style))
        elif line.startswith("**") and line.endswith("**"):
            story.append(Paragraph(f"<b>{line[2:-2]}</b>", body_style))
        elif line.startswith("|"):
            pass  # skip table lines — handled separately
        else:
            # Replace markdown bold **text** inline
            formatted = line.replace("**", "<b>", 1)
            while "**" in formatted:
                formatted = formatted.replace("**", "</b>", 1)
            story.append(Paragraph(formatted, body_style))

    # ── Footer ────────────────────────────────────────────────────────
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("arhatinfo.com · hello@arhatinfo.com", meta_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()