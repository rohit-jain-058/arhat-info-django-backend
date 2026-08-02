"""
PDF Tools views — merge and compress PDFs.

Requirements:
  pip install pypdf pikepdf

Routes:
  POST /api/tools/pdf/merge/   — merge multiple PDFs
  POST /api/tools/pdf/minify/  — compress a single PDF
"""
import io
import logging
import tempfile
import os

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


# ── PDF MERGE ─────────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def pdf_merge(request):
    """
    Merge multiple uploaded PDFs into one in the order provided.

    POST /api/tools/pdf/merge/
    Form fields:
      file_0, file_1, ...  → PDF files
      order_0, order_1,... → integer order (optional)
    """
    # Collect files in order
    files = []
    i = 0
    while f'file_{i}' in request.FILES:
        files.append(request.FILES[f'file_{i}'])
        i += 1

    if len(files) < 2:
        return Response({'error': 'At least 2 PDF files required'}, status=400)

    # Validate all are PDFs
    for f in files:
        if not (f.name.endswith('.pdf') or f.content_type == 'application/pdf'):
            return Response({'error': f'{f.name} is not a PDF file'}, status=400)

    try:
        # Try pypdf first (pure Python, no system deps)
        try:
            from pypdf import PdfWriter, PdfReader

            writer = PdfWriter()
            for f in files:
                reader = PdfReader(io.BytesIO(f.read()))
                for page in reader.pages:
                    writer.add_page(page)

            output = io.BytesIO()
            writer.write(output)
            output.seek(0)
            pdf_bytes = output.read()

        except ImportError:
            # Fallback to PyPDF2
            from PyPDF2 import PdfMerger

            merger = PdfMerger()
            for f in files:
                merger.append(io.BytesIO(f.read()))

            output = io.BytesIO()
            merger.write(output)
            merger.close()
            output.seek(0)
            pdf_bytes = output.read()

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="merged.pdf"'
        response['Content-Length']      = len(pdf_bytes)
        return response

    except Exception as e:
        logger.error(f"PDF merge error: {e}", exc_info=True)
        return Response({'error': f'Merge failed: {str(e)}'}, status=500)


# ── PDF MINIFY / COMPRESS ─────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([AllowAny])
def pdf_minify(request):
    """
    Compress a PDF file.

    POST /api/tools/pdf/minify/
    Form fields:
      file  → PDF file
      level → low | medium | high
    """
    if 'file' not in request.FILES:
        return Response({'error': 'No PDF file provided'}, status=400)

    pdf_file = request.FILES['file']
    level    = request.POST.get('level', 'medium')

    if not (pdf_file.name.endswith('.pdf') or pdf_file.content_type == 'application/pdf'):
        return Response({'error': 'File must be a PDF'}, status=400)

    if pdf_file.size > 50 * 1024 * 1024:  # 50MB limit
        return Response({'error': 'File too large. Maximum size is 50MB.'}, status=400)

    try:
        pdf_bytes = _compress_pdf(pdf_file.read(), level)

        out_name = pdf_file.name.replace('.pdf', '_compressed.pdf')
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{out_name}"'
        response['Content-Length']      = len(pdf_bytes)
        return response

    except Exception as e:
        logger.error(f"PDF compress error: {e}", exc_info=True)
        return Response({'error': f'Compression failed: {str(e)}'}, status=500)


def _compress_pdf(pdf_bytes: bytes, level: str) -> bytes:
    """
    Compress PDF using pikepdf (best) or pypdf fallback.
    level: low | medium | high
    """
    # Try pikepdf first — best compression results
    try:
        import pikepdf

        compression_args = {
            'low':    {'compress_streams': True,  'object_stream_mode': pikepdf.ObjectStreamMode.generate,  'recompress_flate': False},
            'medium': {'compress_streams': True,  'object_stream_mode': pikepdf.ObjectStreamMode.generate,  'recompress_flate': True,  'stream_decode_level': pikepdf.StreamDecodeLevel.generalized},
            'high':   {'compress_streams': True,  'object_stream_mode': pikepdf.ObjectStreamMode.generate,  'recompress_flate': True,  'stream_decode_level': pikepdf.StreamDecodeLevel.all},
        }
        args = compression_args.get(level, compression_args['medium'])

        pdf = pikepdf.open(io.BytesIO(pdf_bytes))

        # Remove metadata to save space on high compression
        if level == 'high':
            with pdf.open_metadata() as meta:
                try:
                    meta.clear()
                except Exception:
                    pass

        output = io.BytesIO()
        pdf.save(output, **args)
        output.seek(0)
        result = output.read()
        pdf.close()

        # Return the smaller of original vs compressed
        return result if len(result) < len(pdf_bytes) else pdf_bytes

    except ImportError:
        logger.info("pikepdf not available, using pypdf fallback")

    # Fallback — pypdf compression
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            if level in ('medium', 'high'):
                try:
                    page.compress_content_streams()
                except Exception:
                    pass
            writer.add_page(page)

        # Remove images on high (aggressive)
        if level == 'high':
            writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        result = output.read()

        return result if len(result) < len(pdf_bytes) else pdf_bytes

    except ImportError:
        pass

    # Last resort — PyPDF2
    try:
        from PyPDF2 import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        result = output.read()

        return result if len(result) < len(pdf_bytes) else pdf_bytes

    except ImportError:
        raise ImportError(
            'No PDF library installed. Run: pip install pypdf pikepdf'
        )
