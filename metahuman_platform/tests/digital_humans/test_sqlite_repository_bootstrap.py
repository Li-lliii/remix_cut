from platform_app.modules.digital_humans.repository import DigitalHumanRepository


def test_digital_human_repository_bootstraps_sqlite_url(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'nested' / 'app.db'}"

    created = DigitalHumanRepository(db_url).create(
        name="测试数字人",
        avatar_type="real",
        gender="",
        status="training_pending",
    )

    assert created["name"] == "测试数字人"
    assert DigitalHumanRepository(db_url).get(created["id"])["avatar_type"] == "real"

