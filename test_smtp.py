"""
Quick standalone SMTP send test — no Django required.

Reads the same EMAIL_* variables from your .env that Django uses,
connects, authenticates, and sends one test email. Prints exactly
what step failed if something goes wrong (connect / STARTTLS / auth / send).

Usage:
    python test_smtp.py you@example.com
"""
import base64
import smtplib
import ssl
import sys
from email.mime.text import MIMEText

try:
    from decouple import config
except ImportError:
    import os
    config = lambda key, default=None, cast=str: cast(os.environ.get(key, default)) if os.environ.get(key) is not None else default

EMAIL_HOST          = config('EMAIL_HOST', default='smtp.office365.com')
EMAIL_PORT          = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS       = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')


def manual_auth_login(server, user, password):
    """
    Do the AUTH LOGIN handshake by hand instead of calling server.login().

    Python 3.9.14's smtplib.SMTP.auth() has a str/bytes bug in its base64
    encode path that raises:
        TypeError: can only concatenate str (not "bytes") to str
    on some AUTH LOGIN exchanges. Driving the SMTP commands directly with
    docmd() sidesteps that broken code path entirely.
    """
    code, resp = server.docmd('AUTH', 'LOGIN')
    if code != 334:
        raise smtplib.SMTPAuthenticationError(code, resp)

    code, resp = server.docmd(base64.b64encode(user.encode('ascii')).decode('ascii'))
    if code != 334:
        raise smtplib.SMTPAuthenticationError(code, resp)

    code, resp = server.docmd(base64.b64encode(password.encode('ascii')).decode('ascii'))
    if code != 235:
        raise smtplib.SMTPAuthenticationError(code, resp)

    return code, resp


def main():
    if len(sys.argv) != 2:
        print('Usage: python test_smtp.py you@example.com')
        sys.exit(1)

    to_addr = sys.argv[1]

    if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
        print('EMAIL_HOST_USER / EMAIL_HOST_PASSWORD not set — check your .env')
        sys.exit(1)

    print(f'Host:     {EMAIL_HOST}:{EMAIL_PORT}  (TLS={EMAIL_USE_TLS})')
    print(f'From:     {EMAIL_HOST_USER}')
    print(f'To:       {to_addr}')
    print('-' * 50)

    msg = MIMEText('This is a test email from test_smtp.py — if you got this, SMTP auth works.')
    msg['Subject'] = 'Tylented SMTP test'
    msg['From']    = EMAIL_HOST_USER
    msg['To']      = to_addr

    try:
        print('[1/4] Connecting...')
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=15)
        server.set_debuglevel(0)

        if EMAIL_USE_TLS:
            print('[2/4] Starting TLS...')
            server.starttls(context=ssl.create_default_context())
        else:
            print('[2/4] Skipping TLS (EMAIL_USE_TLS=False)')

        print('[3/4] Authenticating...')
        server.ehlo()
        try:
            server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
        except TypeError:
            # Python 3.9.14 smtplib.auth() str/bytes bug — retry with a
            # manual AUTH LOGIN handshake instead.
            print('      (hit the known Python 3.9.14 smtplib bug — retrying with manual AUTH LOGIN)')
            manual_auth_login(server, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)

        print('[4/4] Sending...')
        server.sendmail(EMAIL_HOST_USER, [to_addr], msg.as_string())
        server.quit()

        print('-' * 50)
        print('SUCCESS — check the inbox (and spam folder) for', to_addr)

    except smtplib.SMTPAuthenticationError as e:
        print('-' * 50)
        print('FAILED at step 3 (authentication):')
        print(f'  {e.smtp_code}: {e.smtp_error.decode(errors="replace")}')
        print('\nIf this is 535 5.7.139 → SMTP AUTH is disabled for this mailbox/tenant.')
        print('If MFA is on for this mailbox, you need an app password, not the real password.')
        sys.exit(1)

    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError) as e:
        print('-' * 50)
        print(f'FAILED at step 1/2 (connection/TLS): {e}')
        print('Check EMAIL_HOST / EMAIL_PORT and that outbound 587 isn\'t blocked by a firewall.')
        sys.exit(1)

    except smtplib.SMTPException as e:
        print('-' * 50)
        print(f'FAILED at step 4 (send): {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
