import psycopg
import pytest
from rheuma_db.testing import can_connect, other_services

SERVICE = "reporting"


def test_can_write_to_own_database(app_cursor):
    app_cursor.execute("SELECT 1")
    assert app_cursor.fetchone() == (1,)


def test_cannot_create_table(app_cursor):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_cursor.execute("CREATE TABLE _isolation_probe (id int)")


@pytest.mark.parametrize("other", other_services(SERVICE))
def test_cannot_connect_to_other_database(db_env, other):
    connected = can_connect(
        host=db_env["host"], port=db_env["port"], dbname=other,
        user=db_env["user"], password=db_env["password"],
    )
    assert connected is False
