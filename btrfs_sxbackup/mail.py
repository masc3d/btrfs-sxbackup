import socket
import subprocess
from email.mime.text import MIMEText


def send(recipient, subject, content):
    if recipient is None:
        return
    if content is None or len(content) == 0:
        return

    # Prepare mail
    msg = MIMEText(content)
    msg['From'] = '%s@%s' % ('btrfs-sxbackup', socket.getfqdn(socket.gethostname()))
    msg['To'] = recipient
    msg['Subject'] = subject

    # Send actual mail using system command
    command = ['sendmail', '-t', '-oi']
    p = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate(msg.as_string().encode('utf-8'))
    retcode = p.wait()
    err_msg = err.decode('utf-8').strip()
    if retcode != 0:
        raise subprocess.CalledProcessError(retcode, command, None)
    if len(err_msg) > 0:
        raise Exception(err_msg)