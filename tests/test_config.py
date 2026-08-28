from pathlib import Path

from cloudinit_lab.config import load_config


def test_load_config_parses_key_value_pairs(tmp_path):
    conf = tmp_path / "test.conf"
    conf.write_text('DEFAULT_RAM=4096\nDEFAULT_VCPUS=4\nROOT_PASSWORD="Test1234!"\n')
    cfg = load_config(conf)
    assert cfg["DEFAULT_RAM"] == 4096
    assert cfg["DEFAULT_VCPUS"] == 4
    assert cfg["ROOT_PASSWORD"] == "Test1234!"


def test_load_config_ignores_comments_and_blank_lines(tmp_path):
    conf = tmp_path / "test.conf"
    conf.write_text("# a comment\n\nDEFAULT_RAM=2048\n")
    cfg = load_config(conf)
    assert cfg["DEFAULT_RAM"] == 2048


def test_load_config_defaults_images_dir_to_repo_root(tmp_path):
    conf = tmp_path / "test.conf"
    conf.write_text("IMAGES_DIR=\n")
    cfg = load_config(conf)
    from cloudinit_lab.config import REPO_ROOT
    assert cfg["IMAGES_DIR"] == REPO_ROOT / "images"


def test_load_config_expands_explicit_images_dir(tmp_path):
    conf = tmp_path / "test.conf"
    conf.write_text('IMAGES_DIR="/opt/cloudinit-lab-images"\n')
    cfg = load_config(conf)
    assert cfg["IMAGES_DIR"] == Path("/opt/cloudinit-lab-images")


def test_bundled_lab_conf_loads_without_error():
    from cloudinit_lab.config import DEFAULT_CONFIG
    cfg = load_config(DEFAULT_CONFIG)
    assert cfg["DEFAULT_RAM"] == 2048
