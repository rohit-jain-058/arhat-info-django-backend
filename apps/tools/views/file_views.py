"""
File tool views — PDF merge, PDF compress.
Image conversion is handled client-side in React (Canvas API).

Endpoints:
  POST /api/tools/pdf/merge/
  POST /api/tools/pdf/minify/
  GET  /api/tools/speedtest/
  POST /api/tools/speedtest/upload/
"""
import io
import logging
import time

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import FileToolLog

logger = logging.getLogger(__name__)


def _get_ip(request) -> str:
    for h in ['HTTP_CF_CONNECTING_IP', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']:
        v = request.META.get(h, '').split(',')[0].strip()
        if v: return v
    return ''


def _log(tool, request, **kwargs):
    try:
        FileToolLog.objects.create(
            tool       = tool,
            ip_address = _get_ip(request),
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:512],
            **kwargs,
        )
    except Exception as e:
        logger.warning(f'File log failed: {e}')


# ── PDF MERGE ──────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def pdf_merge(request):
    """
    Merge multiple PDF files into one.
    Form fields: file_0, file_1, file_2, ...
    """
    start = time.time()
    files = []
    i     = 0
    while f'file_{i}' in request.FILES:
        files.append(request.FILES[f'file_{i}'])
        i += 1

    if len(files) < 2:
        return Response({'error': 'At least 2 PDF files required'}, status=400)

    for f in files:
        if not (f.name.endswith('.pdf') or f.content_type == 'application/pdf'):
            return Response({'error': f'{f.name} is not a PDF'}, status=400)

    total_input = sum(f.size for f in files)

    try:
        pdf_bytes = _merge_pdfs([f.read() for f in files])
    except Exception as e:
        _log('pdf_merge', request, file_count=len(files), input_size=total_input, success=False, error=str(e))
        return Response({'error': f'Merge failed: {e}'}, status=500)

    _log(
        'pdf_merge', request,
        file_count  = len(files),
        input_size  = total_input,
        output_size = len(pdf_bytes),
        duration_ms = int((time.time() - start) * 1000),
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="merged.pdf"'
    response['Content-Length']      = len(pdf_bytes)
    return response


def _merge_pdfs(pdf_bytes_list: list) -> bytes:
    """Try pypdf first, fall back to PyPDF2."""
    try:
        from pypdf import PdfWriter, PdfReader
        writer = PdfWriter()
        for data in pdf_bytes_list:
            reader = PdfReader(io.BytesIO(data))
            for page in reader.pages:
                writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        return output.read()
    except ImportError:
        pass

    try:
        from PyPDF2 import PdfMerger
        merger = PdfMerger()
        for data in pdf_bytes_list:
            merger.append(io.BytesIO(data))
        output = io.BytesIO()
        merger.write(output)
        merger.close()
        output.seek(0)
        return output.read()
    except ImportError:
        raise ImportError('Install pypdf: pip install pypdf')


# ── PDF COMPRESS ───────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def pdf_minify(request):
    """
    Compress a single PDF file.
    Form fields: file, level (low|medium|high)
    """
    start = time.time()
    if 'file' not in request.FILES:
        return Response({'error': 'No file provided'}, status=400)

    pdf_file = request.FILES['file']
    level    = request.POST.get('level', 'medium')

    if pdf_file.size > 50 * 1024 * 1024:
        return Response({'error': 'File too large. Max 50MB.'}, status=400)

    original_bytes = pdf_file.read()
    original_size  = len(original_bytes)

    try:
        compressed = _compress_pdf(original_bytes, level)
    except Exception as e:
        _log('pdf_minify', request, input_size=original_size, success=False, error=str(e))
        return Response({'error': f'Compression failed: {e}'}, status=500)

    compressed_size = len(compressed)
    savings_pct     = max(0, round((1 - compressed_size / original_size) * 100, 1)) if original_size > 0 else 0

    _log(
        'pdf_minify', request,
        input_size  = original_size,
        output_size = compressed_size,
        savings_pct = savings_pct,
        duration_ms = int((time.time() - start) * 1000),
    )

    out_name = pdf_file.name.replace('.pdf', '_compressed.pdf')
    response = HttpResponse(compressed, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{out_name}"'
    response['Content-Length']      = compressed_size
    return response


def _compress_pdf(pdf_bytes: bytes, level: str) -> bytes:
    """Try pikepdf first (best), then pypdf, then PyPDF2."""
    try:
        import pikepdf
        args = {
            'low':    {'compress_streams': True,  'object_stream_mode': pikepdf.ObjectStreamMode.generate, 'recompress_flate': False},
            'medium': {'compress_streams': True,  'object_stream_mode': pikepdf.ObjectStreamMode.generate, 'recompress_flate': True,  'stream_decode_level': pikepdf.StreamDecodeLevel.generalized},
            'high':   {'compress_streams': True,  'object_stream_mode': pikepdf.ObjectStreamMode.generate, 'recompress_flate': True,  'stream_decode_level': pikepdf.StreamDecodeLevel.all},
        }.get(level, {})
        pdf    = pikepdf.open(io.BytesIO(pdf_bytes))
        output = io.BytesIO()
        pdf.save(output, **args)
        output.seek(0)
        result = output.read()
        pdf.close()
        return result if len(result) < len(pdf_bytes) else pdf_bytes
    except ImportError:
        pass

    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            if level in ('medium', 'high'):
                try: page.compress_content_streams()
                except Exception: pass
            writer.add_page(page)
        if level == 'high':
            try: writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
            except Exception: pass
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        result = output.read()
        return result if len(result) < len(pdf_bytes) else pdf_bytes
    except ImportError:
        raise ImportError('Install pypdf or pikepdf: pip install pypdf pikepdf')
