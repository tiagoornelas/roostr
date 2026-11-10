import os
import subprocess
from pathlib import Path

import pytest
from conftest import HostLeakError


def test_firewall_blocks_subprocess_run():
    with pytest.raises(HostLeakError, match="CRITICAL: Test attempted unmocked host OS execution"):
        subprocess.run(["echo", "forbidden"])


def test_firewall_blocks_subprocess_popen():
    with pytest.raises(HostLeakError, match="CRITICAL: Test attempted unmocked host OS execution"):
        subprocess.Popen(["echo", "forbidden"])


def test_firewall_blocks_os_system():
    with pytest.raises(HostLeakError, match="CRITICAL: Test attempted unmocked host OS execution"):
        os.system("echo forbidden")


def test_firewall_sandboxes_home_directory(tmp_path):
    home = os.environ.get("HOME", "")
    assert "sandbox_home" in home
    assert Path(home).is_relative_to(tmp_path)
