"""
Network tool views — IP lookup, DNS, WHOIS, port scan, traceroute, etc.
All endpoints are GET with query params.
Logs usage to IPLookupLog and caches IP data in IPCache.
"""
import io
import os
import socket
import subprocess
import time
import logging
import requests

from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import cache_page
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ..models import IPLookupLog, IPCache

logger = logging.getLogger(__name__)

BLACKLISTS = [
    'zen.spamhaus.org',   'bl.spamcop.net',       'dnsbl.sorbs.net',
    'b.barracudacentral.org', 'dnsbl-1.uceprotect.net', 'psbl.surriel.com',
    'ix.dnsbl.manitu.net', 'dnsbl.dronebl.org',
    'spam.dnsbl.sorbs.net', 'http.dnsbl.sorbs.net',
]

SERVICE_NAMES = {
    21:'FTP', 22:'SSH', 23:'Telnet', 25:'SMTP', 53:'DNS',
    80:'HTTP', 110:'POP3', 143:'IMAP', 443:'HTTPS', 465:'SMTPS',
    587:'SMTP', 993:'IMAPS', 995:'POP3S', 3306:'MySQL',
    5432:'PostgreSQL', 6379:'Redis', 8080:'HTTP-Alt', 8443:'HTTPS-Alt',
    27017:'MongoDB', 5672:'RabbitMQ',
}


def _log(tool, query, request, success=True, error='', duration_ms=None, cached=False):
    try:
        IPLookupLog.objects.create(
            tool          = tool,
            query         = query[:255],
            ip_address    = _get_ip(request),
            user_agent    = request.META.get('HTTP_USER_AGENT', '')[:512],
            success       = success,
            error         = error,
            duration_ms   = duration_ms,
            result_cached = cached,
        )
    except Exception as e:
        logger.warning(f'Log failed: {e}')


def _get_ip(request) -> str:
    for h in ['HTTP_CF_CONNECTING_IP', 'HTTP_X_REAL_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']:
        v = request.META.get(h, '').split(',')[0].strip()
        if v: return v
    return ''


def _get_ip_info(ip: str) -> dict:
    """Get IP geolocation — checks cache first."""
    # Check cache
    try:
        cached = IPCache.objects.get(ip=ip)
        cached.hits += 1
        cached.save(update_fields=['hits'])
        data = cached.data.copy()
        data['cached'] = True
        return data
    except IPCache.DoesNotExist:
        pass

    # Fetch from ipapi.co
    try:
        res = requests.get(
            f'https://ipapi.co/{ip}/json/',
            headers={'User-Agent': 'arhatinfo-tools/1.0'},
            timeout=5,
        )
        d = res.json()
        if not d.get('error'):
            data = {
                'ip':           d.get('ip', ip),
                'version':      d.get('version', '4'),
                'country_name': d.get('country_name'),
                'country_code': d.get('country_code'),
                'region':       d.get('region'),
                'city':         d.get('city'),
                'latitude':     d.get('latitude'),
                'longitude':    d.get('longitude'),
                'timezone':     d.get('timezone'),
                'isp':          d.get('org'),
                'asn':          d.get('asn'),
                'cached':       False,
            }
            # Save to cache
            IPCache.objects.update_or_create(ip=ip, defaults={'data': data})
            return data
    except Exception:
        pass

    # Fallback ip-api.com
    try:
        res = requests.get(
            f'http://ip-api.com/json/{ip}?fields=status,country,countryCode,'
            f'regionName,city,lat,lon,timezone,isp,org,as,query',
            timeout=5,
        )
        d = res.json()
        if d.get('status') == 'success':
            data = {
                'ip':           ip,
                'version':      '6' if ':' in ip else '4',
                'country_name': d.get('country'),
                'country_code': d.get('countryCode'),
                'region':       d.get('regionName'),
                'city':         d.get('city'),
                'latitude':     d.get('lat'),
                'longitude':    d.get('lon'),
                'timezone':     d.get('timezone'),
                'isp':          d.get('isp'),
                'asn':          d.get('as'),
                'cached':       False,
            }
            IPCache.objects.update_or_create(ip=ip, defaults={'data': data})
            return data
    except Exception:
        pass

    return {'ip': ip, 'error': 'Could not fetch location data'}


# ── MY IP ──────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def myip(request):
    start = time.time()
    ip    = _get_ip(request)

    import ipaddress
    try:
        if ipaddress.ip_address(ip).is_private:
            try:
                r  = requests.get('https://api64.ipify.org?format=json', timeout=5)
                ip = r.json().get('ip', ip)
            except Exception:
                pass
    except ValueError:
        pass

    info              = _get_ip_info(ip)
    info['ip']        = ip
    info['version']   = '6' if ':' in ip else '4'
    _log('myip', ip, request, duration_ms=int((time.time()-start)*1000), cached=info.get('cached', False))
    return Response(info)


# ── IP LOOKUP ──────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def iplookup(request):
    start = time.time()
    ip    = request.GET.get('ip', '').strip()
    if not ip:
        return Response({'error': 'ip parameter required'}, status=400)
    info = _get_ip_info(ip)
    _log('iplookup', ip, request, duration_ms=int((time.time()-start)*1000), cached=info.get('cached', False))
    return Response(info)


# ── HOSTNAME LOOKUP ────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def hostname(request):
    start = time.time()
    host  = request.GET.get('host', '').strip()
    if not host:
        return Response({'error': 'host parameter required'}, status=400)
    try:
        try:
            socket.inet_aton(host)
            is_ip = True
        except socket.error:
            is_ip = False

        if is_ip:
            result = socket.gethostbyaddr(host)
            data   = {'input': host, 'ip': host, 'hostname': result[0], 'aliases': result[1]}
        else:
            result = socket.gethostbyname_ex(host)
            data   = {'input': host, 'hostname': host, 'ip': result[2][0] if result[2] else None, 'aliases': result[1], 'all_ips': result[2]}

        _log('hostname', host, request, duration_ms=int((time.time()-start)*1000))
        return Response(data)
    except Exception as e:
        _log('hostname', host, request, success=False, error=str(e))
        return Response({'error': str(e)}, status=400)


# ── WHOIS ──────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def whois(request):
    start  = time.time()
    domain = request.GET.get('domain', '').strip()
    if not domain:
        return Response({'error': 'domain parameter required'}, status=400)
    try:
        import whois as python_whois
        w    = python_whois.whois(domain)
        safe = lambda v: str(v[0] if isinstance(v, list) else v) if v else None
        data = {
            'domain':       domain,
            'registrar':    safe(w.registrar),
            'created':      safe(w.creation_date[0]   if isinstance(w.creation_date, list)   else w.creation_date),
            'expires':      safe(w.expiration_date[0] if isinstance(w.expiration_date, list) else w.expiration_date),
            'updated':      safe(w.updated_date[0]    if isinstance(w.updated_date, list)    else w.updated_date),
            'status':       safe(w.status[0]          if isinstance(w.status, list)          else w.status),
            'name_servers': [ns.lower() for ns in (w.name_servers or [])[:4]],
            'registrant':   safe(getattr(w, 'registrant_name', None) or getattr(w, 'org', None)),
            'country':      safe(w.country),
        }
        _log('whois', domain, request, duration_ms=int((time.time()-start)*1000))
        return Response(data)
    except Exception as e:
        _log('whois', domain, request, success=False, error=str(e))
        return Response({'error': str(e)}, status=500)


# ── BLACKLIST CHECK ────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def blacklist(request):
    start = time.time()
    ip    = request.GET.get('ip', '').strip()
    if not ip:
        return Response({'error': 'ip parameter required'}, status=400)
    try:
        reversed_ip = '.'.join(reversed(ip.split('.')))
    except Exception:
        return Response({'error': 'Invalid IP'}, status=400)

    results, listed = [], 0
    for bl in BLACKLISTS:
        try:
            socket.gethostbyname(f'{reversed_ip}.{bl}')
            results.append({'name': bl, 'listed': True})
            listed += 1
        except socket.gaierror:
            results.append({'name': bl, 'listed': False})

    _log('blacklist', ip, request, duration_ms=int((time.time()-start)*1000))
    return Response({'ip': ip, 'listed_count': listed, 'total_checked': len(BLACKLISTS), 'is_blacklisted': listed > 0, 'blacklists': results})


# ── PORT SCANNER ───────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def portscan(request):
    start     = time.time()
    host      = request.GET.get('host', '').strip()
    ports_str = request.GET.get('ports', '80,443,22,21,25,3306,5432,8080')
    if not host:
        return Response({'error': 'host parameter required'}, status=400)
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        return Response({'error': f'Could not resolve: {host}'}, status=400)

    try:
        port_list = [int(p.strip()) for p in ports_str.split(',') if p.strip()][:20]
    except ValueError:
        return Response({'error': 'Invalid port format'}, status=400)

    results = []
    for port in port_list:
        try:
            s      = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            result = s.connect_ex((ip, port))
            s.close()
            results.append({'port': port, 'status': 'open' if result == 0 else 'closed', 'service': SERVICE_NAMES.get(port, '')})
        except Exception:
            results.append({'port': port, 'status': 'error', 'service': SERVICE_NAMES.get(port, '')})

    _log('portscan', host, request, duration_ms=int((time.time()-start)*1000))
    return Response({'host': host, 'ip': ip, 'ports': results, 'open': len([r for r in results if r['status'] == 'open'])})


# ── TRACEROUTE ─────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def traceroute(request):
    start = time.time()
    host  = request.GET.get('host', '').strip()
    if not host:
        return Response({'error': 'host parameter required'}, status=400)
    try:
        dest_ip = socket.gethostbyname(host)
    except socket.gaierror:
        return Response({'error': f'Could not resolve: {host}'}, status=400)

    hops, timeout = [], 2.0
    for ttl in range(1, 21):
        recv_sock = send_sock = None
        hop_ip = hop_host = rtt = None
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            recv_sock.settimeout(timeout)
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
            import struct, select as sel
            header  = struct.pack('bbHHh', 8, 0, 0, 1, ttl)
            payload = b'arhatinfo'
            import array
            data    = header + payload
            s       = 0
            for i in range(0, len(data), 2):
                w = (data[i] << 8) + (data[i+1] if i+1 < len(data) else 0)
                s += w
            s = (s >> 16) + (s & 0xffff); s += (s >> 16)
            chk    = ~s & 0xffff
            header = struct.pack('bbHHh', 8, 0, socket.htons(chk), 1, ttl)
            start2 = time.time()
            send_sock.sendto(header + payload, (dest_ip, 0))
            if sel.select([recv_sock], [], [], timeout)[0]:
                pkt, addr = recv_sock.recvfrom(1024)
                rtt       = round((time.time() - start2) * 1000, 1)
                hop_ip    = addr[0]
                try: hop_host = socket.gethostbyaddr(hop_ip)[0]
                except: hop_host = hop_ip
        except PermissionError:
            _log('traceroute', host, request, success=False, error='Permission denied')
            return Response({'error': 'Raw sockets not permitted. Run: sudo setcap cap_net_raw+ep $(which python3)'}, status=403)
        except Exception:
            pass
        finally:
            if send_sock: send_sock.close()
            if recv_sock: recv_sock.close()

        hops.append({'hop': ttl, 'ip': hop_ip, 'host': hop_host or hop_ip, 'rtt': rtt, 'timeout': hop_ip is None})
        if hop_ip == dest_ip:
            break

    _log('traceroute', host, request, duration_ms=int((time.time()-start)*1000))
    return Response({'host': host, 'ip': dest_ip, 'hops': hops, 'total_hops': len(hops)})


# ── DNS LOOKUP ─────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def dns_lookup(request):
    start  = time.time()
    domain = request.GET.get('domain', '').strip()
    rtype  = request.GET.get('type', 'A').upper()
    if not domain:
        return Response({'error': 'domain parameter required'}, status=400)
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, rtype)
        records = []
        for r in answers:
            if rtype == 'MX':  records.append({'priority': r.preference, 'host': str(r.exchange)})
            elif rtype == 'SOA': records.append({'mname': str(r.mname), 'rname': str(r.rname), 'serial': r.serial})
            else: records.append(str(r))
        _log('dns', domain, request, duration_ms=int((time.time()-start)*1000))
        return Response({'domain': domain, 'type': rtype, 'records': records})
    except ImportError:
        if rtype == 'A':
            try:
                ips = socket.gethostbyname_ex(domain)[2]
                return Response({'domain': domain, 'type': 'A', 'records': ips})
            except Exception as e:
                return Response({'error': str(e)}, status=500)
        return Response({'error': 'Install dnspython: pip install dnspython'}, status=500)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ── USER AGENT ─────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def useragent(request):
    ua = request.META.get('HTTP_USER_AGENT', '')
    try:
        from user_agents import parse
        p = parse(ua)
        return Response({'raw': ua, 'browser': p.browser.family, 'version': p.browser.version_string, 'os': f'{p.os.family} {p.os.version_string}'.strip(), 'device': p.device.family, 'is_mobile': p.is_mobile, 'is_tablet': p.is_tablet, 'is_bot': p.is_bot})
    except ImportError:
        ua_l = ua.lower()
        browser = 'Chrome' if 'chrome' in ua_l else 'Firefox' if 'firefox' in ua_l else 'Safari' if 'safari' in ua_l else 'Unknown'
        os_name = 'Windows' if 'windows' in ua_l else 'macOS' if 'mac' in ua_l else 'Linux' if 'linux' in ua_l else 'Android' if 'android' in ua_l else 'iOS' if 'iphone' in ua_l else 'Unknown'
        return Response({'raw': ua, 'browser': browser, 'os': os_name, 'is_mobile': any(x in ua_l for x in ['mobile','android','iphone']), 'is_bot': any(x in ua_l for x in ['bot','crawler','spider'])})


# ── SPEED TEST ─────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def speedtest(request):
    size = min(int(request.GET.get('size', 25_000_000)), 50_000_000)
    def stream():
        chunk = os.urandom(65536)
        sent  = 0
        while sent < size:
            yield chunk[:min(65536, size - sent)]
            sent += 65536
    from django.http import StreamingHttpResponse
    response = StreamingHttpResponse(stream(), content_type='application/octet-stream')
    response['Content-Length']  = str(size)
    response['Cache-Control']   = 'no-store'
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def speedtest_upload(request):
    return Response({'received_bytes': len(request.body)})


@api_view(['GET'])
@permission_classes([AllowAny])
def ping(request):
    return Response({'pong': True, 'timestamp': time.time()})
