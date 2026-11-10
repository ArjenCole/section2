"""log_mailer 单测：只验证邮件构造、会话截取与发送时机，不真的联网发信。"""

import pytest

from app.core import log_mailer


class _FakeSMTP:
    """替身 SMTP_SSL：记录 login/send_message 调用，不发任何真实邮件。"""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.logged_in = False
        self.sent = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, message):
        self.sent.append(message)


@pytest.fixture
def reset_state(monkeypatch):
    """重置模块级会话状态，避免用例间串扰。"""
    monkeypatch.setattr(log_mailer, "_sent", False)
    monkeypatch.setattr(log_mailer, "_session_offset", 0)
    # 默认当成“不在不发邮件名单里的普通电脑”，名单相关用例再单独覆盖
    monkeypatch.setattr(log_mailer, "_current_hostname", lambda: "test-pc")
    monkeypatch.delenv("SECTION2_NO_MAIL", raising=False)
    _FakeSMTP.instances.clear()


def _fake_net(monkeypatch, ok=True):
    monkeypatch.setattr(log_mailer, "_net_ok", lambda: ok)


def _session_log_file(tmp_path, monkeypatch, initial="旧会话日志\n"):
    """造一个日志文件并让 log_mailer 指向它。"""
    log_file = tmp_path / "section2.log"
    log_file.write_text(initial, encoding="utf-8")
    monkeypatch.setattr(log_mailer, "log_file_path", lambda: log_file)
    return log_file


def test_build_message_subject_marks_2_0(reset_state):
    """主题带 2.0 标注、收发件人是监督邮箱、附件内容一致。"""
    content = "[2026-11-10 10:00:00] 启动 Section2\n".encode("utf-8")
    message = log_mailer._build_message(
        subject="tester（Section2 2.0.0-alpha.2）",
        body="主机名：PC",
        content=content,
        filename="Section2_261110100000.log",
    )
    assert "2.0" in str(message["Subject"])
    assert message["From"] == log_mailer.MAIL_USER
    assert message["To"] == log_mailer.MAIL_USER
    assert "主机名：PC" in message.get_body(preferencelist=("plain",)).get_content()
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "Section2_261110100000.log"
    assert attachments[0].get_payload(decode=True) == content


def test_read_session_log_only_new_bytes(reset_state, tmp_path, monkeypatch):
    """只发送本次会话新增的部分：偏移之前的内容不进附件。"""
    log_file = _session_log_file(tmp_path, monkeypatch)
    log_mailer.mark_session_offset()
    with log_file.open("ab") as fp:  # 二进制追加：Windows 下文本模式会把 \n 写成 \r\n
        fp.write("本次会话日志\n".encode("utf-8"))
    content = log_mailer._read_session_log()
    assert content == "本次会话日志\n".encode("utf-8")


def test_read_session_log_empty_returns_none(reset_state, tmp_path, monkeypatch):
    """本次会话没有新增日志时返回 None，上层据此跳过发送。"""
    _session_log_file(tmp_path, monkeypatch)
    log_mailer.mark_session_offset()
    assert log_mailer._read_session_log() is None


def test_send_session_log_sends_once(reset_state, tmp_path, monkeypatch):
    """正常发送：SSL 登录监督邮箱，主题带 2.0，附件是本次新增日志；只发一次。"""
    log_file = _session_log_file(tmp_path, monkeypatch)
    log_mailer.mark_session_offset()
    _fake_net(monkeypatch, ok=True)
    monkeypatch.setattr(log_mailer.smtplib, "SMTP_SSL", _FakeSMTP)
    with log_file.open("ab") as fp:
        fp.write("本次会话日志\n".encode("utf-8"))

    log_mailer.send_session_log(join_timeout=5)

    assert len(_FakeSMTP.instances) == 1
    smtp = _FakeSMTP.instances[0]
    assert smtp.logged_in == (log_mailer.MAIL_USER, log_mailer.MAIL_PASSWORD)
    assert len(smtp.sent) == 1
    message = smtp.sent[0]
    assert "2.0" in str(message["Subject"])
    attachment = next(iter(message.iter_attachments()))
    assert attachment.get_payload(decode=True) == "本次会话日志\n".encode("utf-8")

    # 已发送过再调用不再发（退出路径只发一次）
    log_mailer.send_session_log(join_timeout=5)
    assert len(_FakeSMTP.instances) == 1


def test_send_session_log_skips_without_network(reset_state, tmp_path, monkeypatch):
    """无网络则不发送（1.0 SendLog：无网络则不发送），也不起线程。"""
    _session_log_file(tmp_path, monkeypatch)
    log_mailer.mark_session_offset()
    _fake_net(monkeypatch, ok=False)

    def _boom(content):
        raise AssertionError("无网络时不应发起发送")

    monkeypatch.setattr(log_mailer, "_send_quiet", _boom)
    log_mailer.send_session_log(join_timeout=1)
    assert _FakeSMTP.instances == []


def test_send_session_log_skips_on_send_error(reset_state, tmp_path, monkeypatch):
    """发送失败只写日志，不向上抛（退出路径不阻塞），且本次不再重试。"""
    log_file = _session_log_file(tmp_path, monkeypatch)
    log_mailer.mark_session_offset()
    _fake_net(monkeypatch, ok=True)

    def _fail(content):
        raise ConnectionError("smtp 不可用")

    monkeypatch.setattr(log_mailer, "_send_quiet", _fail)
    log_mailer.send_session_log(join_timeout=5)  # 不应抛异常


def test_no_mail_machine_skips_before_network(reset_state, tmp_path, monkeypatch):
    """名单里的电脑不发信，也不做网络探测（连日志都不读）。"""
    monkeypatch.setattr(log_mailer, "_current_hostname", lambda: "JINHE")

    def _no_probe():
        raise AssertionError("不发邮件的电脑不应探测网络")

    def _no_send(content):
        raise AssertionError("不发邮件的电脑不应发起发送")

    monkeypatch.setattr(log_mailer, "_net_ok", _no_probe)
    monkeypatch.setattr(log_mailer, "_send_quiet", _no_send)
    log_mailer.send_session_log(join_timeout=1)
    assert _FakeSMTP.instances == []


def test_no_mail_host_match_ignores_case_and_domain(reset_state, monkeypatch):
    """主机名比较忽略大小写与域后缀；不在名单的机器照常发送。"""
    monkeypatch.setattr(log_mailer, "_current_hostname", lambda: "JINHE")
    assert log_mailer._is_no_mail_machine()
    monkeypatch.setattr(log_mailer, "_current_hostname", lambda: "jinhe.corp.local")
    assert log_mailer._is_no_mail_machine()
    monkeypatch.setattr(log_mailer, "_current_hostname", lambda: "desktop-abc")
    assert not log_mailer._is_no_mail_machine()


def test_env_override_skips_mail(reset_state, monkeypatch):
    """SECTION2_NO_MAIL=1 可强制跳过（与主机名无关）。"""
    monkeypatch.setattr(log_mailer, "_current_hostname", lambda: "desktop-abc")
    monkeypatch.setenv("SECTION2_NO_MAIL", "1")
    assert log_mailer._is_no_mail_machine()
    monkeypatch.setenv("SECTION2_NO_MAIL", "0")
    assert not log_mailer._is_no_mail_machine()
