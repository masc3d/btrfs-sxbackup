import subprocess


def create_subprocess_args(cmd, url=None):
    """
    Create subprocess arguments for shell command/args to be executed
    Internally Wraps command into ssh call if url host name is not None
    :param cmd: Shell command string or argument list
    :param url: url of remote host
    :return: Subprocess arguments
    """
    # in case cmd is a regular value, convert to list
    cmd = cmd if isinstance(cmd, list) else [cmd]
    # wrap into bash or ssh command respectively
    # depending if command is executed locally (host==None) or remotely
    subprocess_args = ['bash', '-c'] + cmd if url is None or url.hostname is None else \
        ['ssh', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', '%s@%s'
         % (url.username, url.hostname)] + cmd

    return subprocess_args


def exists(command, url=None):
    """
    Check if shell command exists
    :param command: Command to verify
    :param url: url of remote host
    :return: True if location exists, otherwise False
    """
    type_prc = subprocess.Popen(create_subprocess_args(['type ' + command], url),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                shell=False)
    return type_prc.wait() == 0


