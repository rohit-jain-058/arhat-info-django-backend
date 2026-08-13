# apps/resumes/views.py
import json
import io
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from openai import OpenAI

from .models import Resume
from .serializers import ResumeSerializer, ResumeUploadSerializer, ResumeEditSerializer

MAX_RESUMES = 5
client      = OpenAI(api_key=settings.OPENAI_API_KEY)


# ── Extract text from PDF ─────────────────────────────────────────
def extract_text_from_file(file):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file.read())) as pdf:
            text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        return text.strip()
    except Exception:
        pass

    # Fallback: pypdf
    try:
        from pypdf import PdfReader
        file.seek(0)
        reader = PdfReader(io.BytesIO(file.read()))
        text   = '\n'.join(page.extract_text() or '' for page in reader.pages)
        return text.strip()
    except Exception:
        pass

    # DOCX fallback
    try:
        from docx import Document
        file.seek(0)
        doc  = Document(io.BytesIO(file.read()))
        text = '\n'.join(p.text for p in doc.paragraphs)
        return text.strip()
    except Exception:
        return ''


# ── Parse resume with GPT-4o ──────────────────────────────────────
def parse_resume_with_ai(raw_text):
    prompt = f"""You are a resume parser. Extract structured information from the resume text below.

Return ONLY valid JSON with this exact structure:
{{
  "skills": ["skill1", "skill2", ...],
  "experience": [
    {{
      "company": "Company Name",
      "role": "Job Title",
      "duration": "Jan 2022 - Present",
      "years": 2.5,
      "description": "Brief description of responsibilities"
    }}
  ],
  "achievements": [
    "Achievement 1 with metrics if available",
    "Achievement 2"
  ],
  "years_experience": 5.5,
  "career_goal": "Inferred career goal or objective based on experience trajectory",
  "summary": "2-3 sentence professional summary"
}}

Rules:
- skills: list of technical and soft skills, max 20
- experience: all work experiences, most recent first
- achievements: quantified achievements only, max 10
- years_experience: total years of professional experience as a decimal
- career_goal: infer from the resume if not explicitly stated
- summary: concise professional summary suitable for a resume header

Resume text:
{raw_text[:8000]}

Return only the JSON, no explanation."""

    response = client.chat.completions.create(
        model      = 'gpt-4o',
        max_tokens = 1500,
        messages   = [{'role': 'user', 'content': prompt}],
        response_format = {'type': 'json_object'},
    )
    text = response.choices[0].message.content or '{}'

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}

    return {
        'skills':           data.get('skills', []),
        'experience':       data.get('experience', []),
        'achievements':     data.get('achievements', []),
        'years_experience': data.get('years_experience'),
        'career_goal':      data.get('career_goal', ''),
        'summary':          data.get('summary', ''),
    }


# ── List resumes ──────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_resumes(request):
    resumes = Resume.objects.filter(user=request.user)
    return Response({
        'resumes': ResumeSerializer(resumes, many=True, context={'request': request}).data,
        'count':   resumes.count(),
        'limit':   MAX_RESUMES,
    })


# ── Upload resume ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_resume(request):
    # Check limit
    count = Resume.objects.filter(user=request.user).count()
    if count >= MAX_RESUMES:
        return Response(
            {'error': f'You can save up to {MAX_RESUMES} resumes. Delete one to add another.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ResumeUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    file      = serializer.validated_data['file']
    name      = serializer.validated_data['name']
    raw_text  = extract_text_from_file(file)

    if not raw_text:
        return Response({'error': 'Could not extract text from the file. Try a different PDF.'}, status=400)

    # Parse with AI
    try:
        ai_data = parse_resume_with_ai(raw_text)
        ai_processed = True
    except Exception as e:
        ai_data      = {'skills': [], 'experience': [], 'achievements': [], 'years_experience': None, 'career_goal': '', 'summary': ''}
        ai_processed = False

    # Save
    file.seek(0)
    resume = Resume.objects.create(
        user             = request.user,
        name             = name,
        file             = file,
        raw_text         = raw_text,
        ai_processed     = ai_processed,
        **ai_data,
    )

    return Response(
        ResumeSerializer(resume, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


# ── Get single resume ─────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_resume(request, pk):
    try:
        resume = Resume.objects.get(pk=pk, user=request.user)
    except Resume.DoesNotExist:
        return Response({'error': 'Resume not found'}, status=404)
    return Response(ResumeSerializer(resume, context={'request': request}).data)


# ── Update resume ─────────────────────────────────────────────────
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_resume(request, pk):
    try:
        resume = Resume.objects.get(pk=pk, user=request.user)
    except Resume.DoesNotExist:
        return Response({'error': 'Resume not found'}, status=404)

    serializer = ResumeEditSerializer(resume, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    serializer.save()
    return Response(ResumeSerializer(resume, context={'request': request}).data)


# ── Delete resume ─────────────────────────────────────────────────
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_resume(request, pk):
    try:
        resume = Resume.objects.get(pk=pk, user=request.user)
    except Resume.DoesNotExist:
        return Response({'error': 'Resume not found'}, status=404)

    # Delete file from storage
    if resume.file:
        resume.file.delete(save=False)
    resume.delete()
    return Response({'message': 'Resume deleted'}, status=204)


# ── Re-parse resume with AI ───────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reparse_resume(request, pk):
    try:
        resume = Resume.objects.get(pk=pk, user=request.user)
    except Resume.DoesNotExist:
        return Response({'error': 'Resume not found'}, status=404)

    if not resume.raw_text:
        return Response({'error': 'No text to parse'}, status=400)

    try:
        ai_data = parse_resume_with_ai(resume.raw_text)
        for key, val in ai_data.items():
            setattr(resume, key, val)
        resume.ai_processed = True
        resume.save()
    except Exception as e:
        return Response({'error': str(e)}, status=500)

    return Response(ResumeSerializer(resume, context={'request': request}).data)
