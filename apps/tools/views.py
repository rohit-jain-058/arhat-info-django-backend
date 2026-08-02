"""
IP Tools views — all 10 tools.
All endpoints are GET with query params.

Routes:
  /api/tools/myip/
  /api/tools/iplookup/?ip=8.8.8.8
  /api/tools/hostname/?host=google.com
  /api/tools/whois/?domain=google.com
  /api/tools/blacklist/?ip=1.2.3.4
  /api/tools/portscan/?host=google.com&ports=80,443,22
  /api/tools/traceroute/?host=google.com
  /api/tools/dns/?domain=google.com&type=A
  /api/tools/useragent/
  /api/tools/speedtest/
  /api/tools/ping/
"""
import json
import socket
from django.core.cache import cache
import os
import time
from django.http import StreamingHttpResponse, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

import time
import subprocess
import logging
import requests
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from apps.subscriptions.permissions import IsAIToolsSubscriber
from ai_usage import ai_tool_endpoint
from gpt_service import (
    generate_upwork_proposal,
    generate_recruiter_reply,
    match_job_description,
    generate_cron,
    analyze_api_request,
)
logger = logging.getLogger(__name__)





# ── 1. UPWORK PROPOSAL GENERATOR ──────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('upwork_proposal')
def upwork_proposal_generator(request):
    job_description = request.data.get('job_description', '').strip()
    skills          = request.data.get('skills', '').strip()
    experience      = request.data.get('experience', '').strip()
    rate            = request.data.get('rate', '')
    tone            = request.data.get('tone', 'professional')

    if not job_description:
        raise ValueError('job_description is required')
    if not skills:
        raise ValueError('skills is required')

    inputs = {
        'job_description': job_description[:3000],
        'skills':          skills,
        'experience':      experience,
        'rate':            rate,
        'tone':            tone,
    }
    result = generate_upwork_proposal(job_description, skills, experience, rate, tone)
    return result, inputs


# ── 2. LINKEDIN RECRUITER REPLY ────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('recruiter_reply')
def recruiter_reply_generator(request):
    recruiter_message = request.data.get('recruiter_message', '').strip()
    situation         = request.data.get('situation', 'ask_more')
    user_name         = request.data.get('name', '')
    tone              = request.data.get('tone', 'professional')

    if not recruiter_message:
        raise ValueError('recruiter_message is required')

    valid_situations = ['interested', 'not_interested', 'maybe', 'ask_more']
    if situation not in valid_situations:
        situation = 'ask_more'

    inputs = {
        'recruiter_message': recruiter_message[:2000],
        'situation':         situation,
        'name':              user_name,
        'tone':              tone,
    }
    result = generate_recruiter_reply(recruiter_message, situation, user_name, tone)
    return result, inputs


# ── 3. JOB DESCRIPTION MATCHER ────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('job_matcher')
def job_description_matcher(request):
    job_description    = request.data.get('job_description', '').strip()
    resume_or_skills   = request.data.get('resume_or_skills', '').strip()
    output_format      = request.data.get('output_format', 'analysis')

    if not job_description:
        raise ValueError('job_description is required')
    if not resume_or_skills:
        raise ValueError('resume_or_skills is required')

    valid_formats = ['analysis', 'cover_letter', 'keywords', 'gap_analysis']
    if output_format not in valid_formats:
        output_format = 'analysis'

    inputs = {
        'job_description':  job_description[:3000],
        'resume_or_skills': resume_or_skills[:3000],
        'output_format':    output_format,
    }
    result = match_job_description(job_description, resume_or_skills, output_format)
    return result, inputs


# ── 4. CRON GENERATOR ─────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('cron_gen')
def cron_generator(request):
    description = request.data.get('description', '').strip()
    timezone    = request.data.get('timezone', 'UTC')
    format_type = request.data.get('format', 'standard')

    if not description:
        raise ValueError('description is required')

    valid_formats = ['standard', 'quartz', 'aws']
    if format_type not in valid_formats:
        format_type = 'standard'

    inputs = {
        'description': description,
        'timezone':    timezone,
        'format':      format_type,
    }
    result = generate_cron(description, timezone, format_type)
    return result, inputs


# ── 5. API TESTER ─────────────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAIToolsSubscriber])
@ai_tool_endpoint('api_tester')
def api_tester(request):
    method          = request.data.get('method', 'GET').upper()
    url             = request.data.get('url', '').strip()
    headers         = request.data.get('headers', '')
    body            = request.data.get('body', '')
    response_status = request.data.get('response_status', '')
    response_body   = request.data.get('response_body', '')
    question        = request.data.get('question', '')

    if not url:
        raise ValueError('url is required')

    valid_methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
    if method not in valid_methods:
        method = 'GET'

    inputs = {
        'method':          method,
        'url':             url,
        'headers':         headers[:2000],
        'body':            body[:3000],
        'response_status': response_status,
        'response_body':   response_body[:3000],
        'question':        question,
    }
    result = analyze_api_request(
        method, url, headers, body,
        response_status, response_body, question
    )
    return result, inputs

# Free IP geolocation API — no key needed
IP_API_URL = "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as,query"


def _get_ip_info(ip: str) -> dict:
    # ipapi.co handles both IPv4 and IPv6
    try:
        res = requests.get(
            f"https://ipapi.co/{ip}/json/",
            headers={"User-Agent": "arhatinfo-tools/1.0"},
            timeout=5,
        )
        d = res.json()
        if not d.get("error"):
            return {
                "ip":           ip,          # ← use the IP we passed in, not what they return
                "country_name": d.get("country_name"),
                "country_code": d.get("country_code"),
                "region":       d.get("region"),
                "city":         d.get("city"),
                "latitude":     d.get("latitude"),
                "longitude":    d.get("longitude"),
                "timezone":     d.get("timezone"),
                "isp":          d.get("org"),
                "asn":          d.get("asn"),
                "is_vpn":       False,
                "is_proxy":     False,
            }
    except Exception:
        pass

    # Fallback — ip-api.com (IPv4 only, for when ipapi.co fails)
    try:
        # For IPv6 convert to IPv4 if possible for fallback lookup
        lookup_ip = ip
        res = requests.get(
            f"http://ip-api.com/json/{lookup_ip}?fields=status,country,countryCode,"
            f"regionName,city,lat,lon,timezone,isp,org,as,proxy,hosting",
            timeout=5,
        )
        d = res.json()
        if d.get("status") == "success":
            return {
                "ip":           ip,          # ← always original IP
                "country_name": d.get("country"),
                "country_code": d.get("countryCode"),
                "region":       d.get("regionName"),
                "city":         d.get("city"),
                "latitude":     d.get("lat"),
                "longitude":    d.get("lon"),
                "timezone":     d.get("timezone"),
                "isp":          d.get("isp"),
                "asn":          d.get("as"),
                "is_vpn":       d.get("hosting", False),
                "is_proxy":     d.get("proxy", False),
            }
    except Exception:
        pass

    return {"ip": ip, "error": "Could not fetch location data"}

# ── 1. MY IP ──────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def myip(request):
    # Get real IP from headers
    ip = None
    for header in [
        'HTTP_CF_CONNECTING_IP',
        'HTTP_X_REAL_IP',
        'HTTP_X_FORWARDED_FOR',
        'REMOTE_ADDR',
    ]:
        val = request.META.get(header, '').strip()
        if val:
            ip = val.split(',')[0].strip()
            break

    if not ip:
        return Response({'error': 'Could not detect IP'}, status=400)

    # Determine version BEFORE looking up
    is_ipv6 = ':' in ip
    version  = '6' if is_ipv6 else '4'

    # For local dev — fetch real public IP from ipify
    if ip in ('127.0.0.1', '::1', ''):
        try:
            res = requests.get('https://api64.ipify.org?format=json', timeout=5)
            ip  = res.json().get('ip', '127.0.0.1')
            is_ipv6 = ':' in ip
            version  = '6' if is_ipv6 else '4'
        except Exception:
            pass

    info          = _get_ip_info(ip)
    info['ip']    = ip       # ← always show the ORIGINAL detected IP
    info['version'] = version  # ← always show correct version
    return Response(info)

# ── 2. IP LOOKUP ──────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def iplookup(request):
    """Look up any IP address."""
    ip = request.GET.get('ip', '').strip()
    if not ip:
        return Response({'error': 'ip parameter required'}, status=400)
    return Response(_get_ip_info(ip))


# ── 3. HOSTNAME LOOKUP ────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def hostname(request):
    """Resolve hostname → IP or IP → hostname."""
    host = request.GET.get('host', '').strip()
    if not host:
        return Response({'error': 'host parameter required'}, status=400)

    try:
        # Check if input is an IP or hostname
        try:
            socket.inet_aton(host)
            is_ip = True
        except socket.error:
            is_ip = False

        if is_ip:
            # IP → hostname
            hostname_result = socket.gethostbyaddr(host)
            return Response({
                'input':    host,
                'ip':       host,
                'hostname': hostname_result[0],
                'aliases':  hostname_result[1],
            })
        else:
            # Hostname → IP
            ip_result = socket.gethostbyname_ex(host)
            return Response({
                'input':    host,
                'hostname': host,
                'ip':       ip_result[2][0] if ip_result[2] else None,
                'aliases':  ip_result[1],
                'all_ips':  ip_result[2],
            })
    except socket.herror as e:
        return Response({'error': f'Could not resolve: {e}'}, status=400)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ── 4. WHOIS ──────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def whois(request):
    """WHOIS lookup for a domain or IP."""
    domain = request.GET.get('domain', '').strip()
    if not domain:
        return Response({'error': 'domain parameter required'}, status=400)

    try:
        import whois as python_whois
        w = python_whois.whois(domain)

        def safe(val):
            if isinstance(val, list):
                return [str(v) for v in val[:3]]
            return str(val) if val else None

        return Response({
            'domain':       domain,
            'registrar':    safe(w.registrar),
            'created':      safe(w.creation_date[0] if isinstance(w.creation_date, list) else w.creation_date),
            'expires':      safe(w.expiration_date[0] if isinstance(w.expiration_date, list) else w.expiration_date),
            'updated':      safe(w.updated_date[0] if isinstance(w.updated_date, list) else w.updated_date),
            'status':       safe(w.status[0] if isinstance(w.status, list) else w.status),
            'name_servers': [ns.lower() for ns in (w.name_servers or [])[:4]],
            'registrant':   safe(w.get('registrant_name') or w.get('org')),
            'country':      safe(w.country),
        })
    except ImportError:
        # python-whois not installed — use subprocess
        try:
            result = subprocess.run(
                ['whois', domain],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout[:2000]
            return Response({'domain': domain, 'raw': lines})
        except Exception as e:
            return Response({'error': f'WHOIS unavailable: install python-whois'}, status=500)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ── 5. BLACKLIST CHECK ────────────────────────────────────────────────
BLACKLISTS = [
    'zen.spamhaus.org',
    'bl.spamcop.net',
    'dnsbl.sorbs.net',
    'b.barracudacentral.org',
    'dnsbl-1.uceprotect.net',
    'psbl.surriel.com',
    'ix.dnsbl.manitu.net',
    'dnsbl.dronebl.org',
    'spam.dnsbl.sorbs.net',
    'http.dnsbl.sorbs.net',
]

@api_view(['GET'])
@permission_classes([AllowAny])
def blacklist(request):
    """Check if an IP is on any spam blacklists."""
    ip = request.GET.get('ip', '').strip()
    if not ip:
        return Response({'error': 'ip parameter required'}, status=400)

    # Reverse the IP for DNSBL lookups
    try:
        reversed_ip = '.'.join(reversed(ip.split('.')))
    except Exception:
        return Response({'error': 'Invalid IP address'}, status=400)

    results = []
    listed_count = 0

    for bl in BLACKLISTS:
        lookup = f"{reversed_ip}.{bl}"
        try:
            socket.gethostbyname(lookup)
            # Got a response = listed
            results.append({'name': bl, 'listed': True})
            listed_count += 1
        except socket.gaierror:
            # No response = not listed
            results.append({'name': bl, 'listed': False})
        except Exception:
            results.append({'name': bl, 'listed': False})

    return Response({
        'ip':             ip,
        'listed_count':   listed_count,
        'total_checked':  len(BLACKLISTS),
        'is_blacklisted': listed_count > 0,
        'blacklists':     results,
    })


# ── 6. PORT SCANNER ───────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def portscan(request):
    """Scan specific ports on a host."""
    host  = request.GET.get('host', '').strip()
    ports_str = request.GET.get('ports', '80,443,22,21,25,3306,5432,8080')

    if not host:
        return Response({'error': 'host parameter required'}, status=400)

    # Resolve hostname to IP
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return Response({'error': f'Could not resolve hostname: {host}'}, status=400)

    # Parse ports
    try:
        port_list = [int(p.strip()) for p in ports_str.split(',') if p.strip()]
        port_list = [p for p in port_list if 1 <= p <= 65535][:20]  # max 20 ports
    except ValueError:
        return Response({'error': 'Invalid port format. Use comma-separated numbers.'}, status=400)

    SERVICE_NAMES = {
        21:'FTP', 22:'SSH', 23:'Telnet', 25:'SMTP', 53:'DNS',
        80:'HTTP', 110:'POP3', 143:'IMAP', 443:'HTTPS', 465:'SMTPS',
        587:'SMTP', 993:'IMAPS', 995:'POP3S', 3306:'MySQL',
        5432:'PostgreSQL', 6379:'Redis', 8080:'HTTP-Alt', 8443:'HTTPS-Alt',
        27017:'MongoDB', 5672:'RabbitMQ',
    }

    results = []
    for port in port_list:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((ip, port))
            sock.close()
            results.append({
                'port':    port,
                'status':  'open' if result == 0 else 'closed',
                'service': SERVICE_NAMES.get(port, ''),
            })
        except Exception:
            results.append({'port': port, 'status': 'error', 'service': SERVICE_NAMES.get(port, '')})

    return Response({
        'host':  host,
        'ip':    ip,
        'ports': results,
        'open':  len([r for r in results if r['status'] == 'open']),
    })


# ── 7. TRACEROUTE ─────────────────────────────────────────────────────



@api_view(['GET'])
@permission_classes([AllowAny])
def traceroute(request):
    host = request.GET.get('host', '').strip()
    if not host:
        return Response({'error': 'host parameter required'}, status=400)

    # Cache traceroute results for 1 hour — same host rarely changes
    cache_key = f"traceroute_{host}"
    cached    = cache.get(cache_key)
    if cached:
        return Response(cached)

    """
    Network path analysis using TCP probing.
    Real traceroute requires raw sockets which are not available
    on shared/restricted hosting. This uses TCP connect timing
    to show reachability and latency at each TTL level.
    """
    try:
        max_hops= min(int(request.GET.get('max_hops', 15)), 20)

        if not host:
            return Response({'error': 'host parameter required'}, status=400)

        # Resolve hostname
        try:
            dest_ip = socket.gethostbyname(host)
        except socket.gaierror:
            return Response({'error': f'Could not resolve: {host}'}, status=400)

        hops    = []
        timeout = 2
        # Try port 443 first, fallback to 80
        ports   = [443, 80, 53]

        for ttl in range(1, max_hops + 1):
            hop_ip  = None
            hop_host= None
            rtt     = None

            for port in ports:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
                s.settimeout(timeout)
                start = time.time()
                try:
                    err = s.connect_ex((dest_ip, port))
                    elapsed = round((time.time() - start) * 1000, 1)
                    # 0 = connected, 111 = connection refused — both mean we reached the host
                    if err in (0, 111, 10061):
                        hop_ip  = dest_ip
                        rtt     = elapsed
                        break
                except socket.timeout:
                    pass
                except Exception:
                    pass
                finally:
                    s.close()

                if hop_ip:
                    break

            # Try reverse DNS if we got an IP
            if hop_ip:
                try:
                    hop_host = socket.gethostbyaddr(hop_ip)[0]
                except Exception:
                    hop_host = hop_ip

            hops.append({
                'hop':    ttl,
                'ip':     hop_ip,
                'host':   hop_host or hop_ip,
                'rtt':    rtt,
                'status': 'reached' if hop_ip == dest_ip else ('timeout' if not hop_ip else 'intermediate'),
            })

            # Stop when we reach the destination
            if hop_ip == dest_ip:
                break
        result = {
            'host':        host,
            'ip':          dest_ip,
            'hops':        hops,
            'total_hops':  len(hops),
            'method':      'tcp',
            'note':        'Using TCP probing — intermediate hops not visible on restricted servers',
        }
        cache.set(cache_key, result, timeout=3600)   # cache 1 hour
        return Response(result)
    except requests.Timeout:
        return Response({'error': 'Traceroute timed out — host may be unreachable'}, status=408)
    except Exception as e:
        logger.error(f"Traceroute error: {e}")
        return Response({'error': str(e)}, status=500)

    
# ── 8. DNS LOOKUP ─────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def dns_lookup(request):
    """DNS record lookup."""
    domain    = request.GET.get('domain', '').strip()
    record_type = request.GET.get('type', 'A').upper()

    if not domain:
        return Response({'error': 'domain parameter required'}, status=400)

    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, record_type)
        records = []
        for r in answers:
            if record_type == 'MX':
                records.append({'priority': r.preference, 'host': str(r.exchange)})
            elif record_type == 'SOA':
                records.append({
                    'mname': str(r.mname), 'rname': str(r.rname),
                    'serial': r.serial, 'refresh': r.refresh,
                })
            else:
                records.append(str(r))
        return Response({'domain': domain, 'type': record_type, 'records': records})
    except ImportError:
        # dnspython not installed — use socket for A records
        if record_type == 'A':
            try:
                ips = socket.gethostbyname_ex(domain)[2]
                return Response({'domain': domain, 'type': 'A', 'records': ips})
            except Exception as e:
                return Response({'error': str(e)}, status=500)
        return Response({'error': 'Install dnspython for full DNS support: pip install dnspython'}, status=500)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ── 9. USER AGENT ─────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def useragent(request):
    """Parse the request's User-Agent string."""
    ua_string = request.META.get('HTTP_USER_AGENT', '')

    try:
        from user_agents import parse
        ua = parse(ua_string)
        return Response({
            'raw':       ua_string,
            'browser':   ua.browser.family,
            'version':   ua.browser.version_string,
            'os':        f"{ua.os.family} {ua.os.version_string}".strip(),
            'device':    ua.device.family,
            'engine':    ua.browser.family,
            'is_mobile': ua.is_mobile,
            'is_tablet': ua.is_tablet,
            'is_bot':    ua.is_bot,
        })
    except ImportError:
        # user-agents not installed — basic parsing
        ua_lower = ua_string.lower()
        browser  = 'Unknown'
        os_name  = 'Unknown'
        if 'chrome' in ua_lower:    browser = 'Chrome'
        elif 'firefox' in ua_lower: browser = 'Firefox'
        elif 'safari' in ua_lower:  browser = 'Safari'
        elif 'edge' in ua_lower:    browser = 'Edge'
        if 'windows' in ua_lower:   os_name = 'Windows'
        elif 'mac' in ua_lower:     os_name = 'macOS'
        elif 'linux' in ua_lower:   os_name = 'Linux'
        elif 'android' in ua_lower: os_name = 'Android'
        elif 'iphone' in ua_lower:  os_name = 'iOS'
        return Response({
            'raw':       ua_string,
            'browser':   browser,
            'version':   '',
            'os':        os_name,
            'device':    'Mobile' if any(x in ua_lower for x in ['mobile','android','iphone']) else 'Desktop',
            'engine':    browser,
            'is_mobile': any(x in ua_lower for x in ['mobile','android','iphone']),
            'is_tablet': 'ipad' in ua_lower,
            'is_bot':    any(x in ua_lower for x in ['bot','crawler','spider']),
        })


# ── 10. SPEED TEST ────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def speedtest(request):
    """
    Serve random bytes for download speed test.
    Uses streaming so Django doesn't buffer the whole thing in memory.
    Add Cache-Control: no-store so browsers don't cache it.
    """
    size = min(int(request.GET.get('size', 3_000_000)), 50_000_000)

    def stream_bytes():
        chunk = os.urandom(65536)   # 64KB random chunks (can't be cached/compressed)
        sent  = 0
        while sent < size:
            remaining = size - sent
            yield chunk[:min(65536, remaining)]
            sent += 65536

    response = StreamingHttpResponse(
        stream_bytes(),
        content_type='application/octet-stream',
    )
    response['Content-Length']  = str(size)
    response['Cache-Control']   = 'no-store, no-cache, must-revalidate'
    response['Pragma']          = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def speedtest_upload(request):
    """
    Receive upload data and return the size received.
    The browser measures how long it took to send.
    """
    received = len(request.body)
    return Response({
        'received_bytes': received,
        'received_mb':    round(received / 1_000_000, 2),
        'timestamp':      time.time(),
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def ping(request):
    """
    Minimal ping endpoint.
    Returns server timestamp so browser can measure RTT.
    """
    return Response({
        'pong':      True,
        'timestamp': time.time(),
    })