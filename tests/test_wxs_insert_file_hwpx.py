from pathlib import Path
from unittest.mock import Mock

from src.jb_quickpanel.bridges.wxs_bridge import WxsHwpBridge


def _bridge():
    bridge = object.__new__(WxsHwpBridge)
    bridge.ensure = Mock(return_value=(True, "ok"))
    bridge._create_action = Mock(return_value=object())
    bridge._action_create_set = Mock(return_value=object())
    bridge._action_get_default = Mock()
    bridge._set_item = Mock(return_value=True)
    bridge._action_execute = Mock(return_value=1)
    bridge.restore_focus = Mock()
    bridge.reset = Mock()
    return bridge


def test_hwpx_insert_is_rejected_before_connection():
    bridge = _bridge()
    form = Path(__file__).resolve().parents[1] / "kedufine_forms" / "plan.hwpx"

    ok, message = bridge.insert_file(str(form))

    assert not ok
    assert "HWP" in message
    bridge.ensure.assert_not_called()
    bridge._action_execute.assert_not_called()


def test_hwpx_insert_never_attempts_file_format_parameter():
    bridge = _bridge()
    form = Path(__file__).resolve().parents[1] / "kedufine_forms" / "plan.hwpx"
    ok, message = bridge.insert_file(str(form))

    assert not ok
    assert "HWP" in message
    bridge._set_item.assert_not_called()
    bridge._action_execute.assert_not_called()


def test_hwp_insert_keeps_existing_behavior():
    bridge = _bridge()
    form = Path(__file__).resolve().parents[1] / "kedufine_forms" / "plan.hwp"

    ok, _ = bridge.insert_file(str(form))

    assert ok
    keys = [call.args[1] for call in bridge._set_item.call_args_list]
    assert "FileFormat" not in keys
