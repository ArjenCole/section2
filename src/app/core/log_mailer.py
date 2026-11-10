"""退出时把本次运行的日志作为附件发到监督邮箱（1.0 SendLog 的移植）。

1.0 的做法（section/mcEmail/mscEmail.cs + Program.SendLog）：软件正常退出
前先探测网络，再把本次会话日志发给 section_supviser@163.com——主题填用户
名、正文填主机名、日志文件作附件，发完删掉日志；无网络则直接跳过。

2.0 沿用同一邮箱与授权码，主题在用户名后标注 2.0 版本号。日志按会话截取：
启动时记录日志文件的偏移，退出时只发送本次新增的部分（2.0 的日志文件是
跨会话追加的，不能像 1.0 那样整个文件发完就删）。发送放在后台线程，最多
等 JOIN_TIMEOUT 秒；任何失败只写日志，不影响退出。

开发/自用电脑没必要把日志发到监督邮箱，名单见 NO_MAIL_HOSTS：命中的机器
退出时直接跳过，连网络探测都不做。
"""

from __future__ import annotations

import getpass
import logging
import os
import platform
import smtplib
import socket
import sys
import threading
import time
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from app.core.paths import log_dir
from app.core.version import APP_VERSION

_logger = logging.getLogger("section2.mail")

#: 收件人 = 发件人，同 1.0（section/mcEmail/mscEmail.cs）
MAIL_USER = "section_supviser@163.com"
#: 163 邮箱的授权码（不是登录密码），同 1.0
MAIL_PASSWORD = "section163"
#: SMTP 服务器。1.0 用"smtp." + 发件人域名 + 默认 25 端口明文发信，
#: 现在 163 明文端口已不可用，走 SSL(465)
SMTP_HOST = "smtp.163.com"
SMTP_PORT = 465
#: 连接/读写单次超时（秒）
SMTP_TIMEOUT = 10.0
#: 发信前的连通性探测超时（秒）
NET_CHECK_TIMEOUT = 5.0
#: 退出时等待发送线程的最长时间（秒），超时则交给进程退出回收（daemon）
JOIN_TIMEOUT = 15.0

#: 不发日志邮件的电脑名单（主机名，忽略大小写与域后缀）。
#: 开发/自用电脑不往监督邮箱发日志：命中名单的机器退出时直接跳过，
#: 也不做网络探测。主机名见 Windows「设置 → 系统 → 系统信息 → 设备名称」
#: 或 socket.gethostname()；换机器名后要同步更新这里。
NO_MAIL_HOSTS: frozenset[str] = frozenset({"jinhe"})

_session_offset = 0  # 本次会话日志的起始偏移（启动时记录）
_session_start = time.localtime()  # 本次会话开始时间（附件文件名 / 正文用）
_sent = False  # 本次进程是否已发送过（发送失败也不重试，退出路径只发一次）


def log_file_path() -> Path:
    """当前日志文件（main.setup_logging 写的就是这个路径）。"""
    return log_dir() / "section2.log"


def mark_session_offset() -> None:
    """记录启动时的日志文件大小：退出时只发送本次会话新增的部分。

    必须在 logging.FileHandler 打开之前调用（setup_logging 里 basicConfig 前）。
    """
    global _session_offset, _session_start
    _session_start = time.localtime()
    try:
        _session_offset = log_file_path().stat().st_size
    except OSError:  # 首次运行还没有日志文件
        _session_offset = 0


def _read_session_log() -> bytes | None:
    """读出本次会话写入的日志内容；读不到或没有新增内容返回 None。"""
    path = log_file_path()
    try:
        with path.open("rb") as fp:
            fp.seek(_session_offset)
            content = fp.read()
    except OSError as error:
        _logger.warning("读取日志失败，跳过发送：%s", error)
        return None
    return content or None


def _net_ok() -> bool:
    """发信前探测网络，不通则跳过（对应 1.0 的 mscCheckInternet：无网络不发送）。"""
    try:
        with socket.create_connection((SMTP_HOST, SMTP_PORT), NET_CHECK_TIMEOUT):
            return True
    except OSError as error:
        _logger.info("无网络或 %s 不可达，跳过日志发送：%s", SMTP_HOST, error)
        return False


def _current_hostname() -> str:
    """当前计算机名（单独成函数，便于测试替换）。"""
    return socket.gethostname()


def _short_host(name: str) -> str:
    """主机名归一化：去掉域后缀、忽略大小写，用于和 NO_MAIL_HOSTS 比较。"""
    return name.strip().lower().split(".", 1)[0]


def _is_no_mail_machine() -> bool:
    """本机是否在不发日志邮件的名单里。

    环境变量 SECTION2_NO_MAIL=1 可强制跳过（自动化测试用），与名单无关。
    """
    if os.environ.get("SECTION2_NO_MAIL") == "1":
        return True
    return _short_host(_current_hostname()) in NO_MAIL_HOSTS


def _build_message(subject: str, body: str, content: bytes, filename: str) -> EmailMessage:
    """构造邮件：正文 + 日志附件（对应 1.0 的 mcEmailSender）。"""
    message = EmailMessage()
    message["From"] = MAIL_USER
    message["To"] = MAIL_USER
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message.set_content(body)
    message.add_attachment(
        content, maintype="application", subtype="octet-stream", filename=filename
    )
    return message


def _send(content: bytes) -> None:
    """实际发信。主题沿用 1.0 的"用户名"，后面标注 2.0 版本号。"""
    user = getpass.getuser()
    message = _build_message(
        subject=f"{user}（Section2 {APP_VERSION}）",
        body="\n".join(
            [
                f"主机名：{socket.gethostname()}",  # 1.0 的正文就是主机名
                f"用户名：{user}",
                f"版本：Section2 {APP_VERSION}",
                f"平台：{platform.platform()}，Python {sys.version.split()[0]}",
                f"会话开始：{time.strftime('%Y-%m-%d %H:%M:%S', _session_start)}",
                f"日志文件：{log_file_path()}",
            ]
        ),
        content=content,
        filename=f"Section2_{time.strftime('%y%m%d%H%M%S', _session_start)}.log",
    )
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
        smtp.login(MAIL_USER, MAIL_PASSWORD)
        smtp.send_message(message)


def _send_quiet(content: bytes) -> None:
    """发送并吞掉所有异常：退出路径上不能因为发信报错阻塞/报错。"""
    try:
        _send(content)
        _logger.info("本次会话日志已发送至 %s", MAIL_USER)
    except Exception as error:  # noqa: BLE001 - 退出路径不阻塞
        _logger.warning("日志发送失败：%s", error)


def send_session_log(join_timeout: float = JOIN_TIMEOUT) -> None:
    """程序退出时调用：把本次会话日志作为附件发到监督邮箱。

    不发邮件的电脑（NO_MAIL_HOSTS）、无网络、无新增日志或本次进程已发送过
    则跳过。发送在后台线程进行，最多等待 join_timeout 秒，超时后随进程
    退出回收线程。
    """
    global _sent
    if _sent:
        return
    if _is_no_mail_machine():
        _logger.info("本机（%s）在不发日志邮件的名单里，跳过发送", _current_hostname())
        return
    if not _net_ok():
        return
    content = _read_session_log()
    if content is None:
        return
    _logger.info("发送本次会话日志（%d 字节）至 %s", len(content), MAIL_USER)
    _sent = True
    thread = threading.Thread(
        target=_send_quiet, args=(content,), name="log-mailer", daemon=True
    )
    thread.start()
    thread.join(join_timeout)
    if thread.is_alive():
        _logger.warning("日志发送超过 %.0f 秒仍未完成，不再等待", join_timeout)
