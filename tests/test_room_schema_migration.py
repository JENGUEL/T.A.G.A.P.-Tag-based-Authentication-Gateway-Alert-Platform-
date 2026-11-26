from sqlalchemy import create_engine, inspect

from data.database import _ensure_room_schema


def test_legacy_room_table_gets_room_device_columns():
    database_engine = create_engine("sqlite:///:memory:")
    with database_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE rooms (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO rooms (id, name) VALUES (1, 'Room 201')"
        )

    _ensure_room_schema(database_engine)

    column_names = {
        column["name"] for column in inspect(database_engine).get_columns("rooms")
    }
    assert {"room_number", "section", "quick_actions"} <= column_names
    with database_engine.connect() as connection:
        defaults = connection.exec_driver_sql(
            "SELECT room_number, section, quick_actions FROM rooms WHERE id = 1"
        ).one()
    assert defaults == ("", "", "[]")
    database_engine.dispose()
