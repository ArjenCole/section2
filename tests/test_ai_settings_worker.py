"""跨线程审计回归：AI 设置里的测试连接 QThread 不能挂在对话框下面。

2026-10-27 的 Qt6Core fast-fail 与 ``QThread: Destroyed while thread is still
running`` 的特征一致：worker 作为对话框子对象，对话框关闭时会在 ``run()``
还没返回时析构 QThread。这里锁住修复后的生命周期约定。
"""

from __future__ import annotations


def test_test_connection_worker_is_not_parented_to_dialog(qapp, monkeypatch) -> None:
    from app.views.dialogs import ai_settings_dialog as mod

    # 不真的发网络请求，只验证 worker 的创建/归属
    monkeypatch.setattr(mod._TestConnectionWorker, "start", lambda self: None)
    monkeypatch.setattr(mod.ai_keychain, "get_api_key", lambda _name: "")

    dialog = mod.AiSettingsDialog()
    try:
        dialog._providers = [
            {
                "name": "local",
                "display_name": "Local",
                "base_url": "http://127.0.0.1:1/v1",
                "default_model": "",
            }
        ]
        dialog._selected_index = 0
        dialog._display_name_edit.setText("Local")
        dialog._base_url_edit.setText("http://127.0.0.1:1/v1")
        dialog._temperature_edit.setText("0.2")

        dialog._on_test_connection()

        worker = dialog._test_worker
        assert worker is not None
        # 关键：不是对话框的 QObject 子对象，对话框销毁不会连带析构运行中的线程
        assert worker.parent() is None
        # 模块级集合负责在 finished 之前保住 worker
        assert worker in mod._ACTIVE_TEST_WORKERS
    finally:
        worker = getattr(dialog, "_test_worker", None)
        if worker is not None:
            mod._ACTIVE_TEST_WORKERS.discard(worker)
            worker.deleteLater()
        dialog.deleteLater()
        qapp.processEvents()
