from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.services.service_factory import ServiceFactory


def test_get_all_file_manager_settings(secure_client, secure_client_headers, cheshire_cat):
    file_manager_schemas = ServiceFactory(
        cheshire_cat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).get_schemas()
    response = secure_client.get("/file_manager/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(file_manager_schemas)

    for setting in json["settings"]:
        assert setting["name"] in file_manager_schemas.keys()
        assert setting["value"] == {}
        expected_schema = file_manager_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected file manager
    assert json["selected_configuration"] == "DummyFileManagerConfig"


def test_get_file_manager_settings_non_existent(secure_client, secure_client_headers):
    non_existent_filemanager_name = "FileManagerNonExistentConfig"
    response = secure_client.get(
        f"/file_manager/settings/{non_existent_filemanager_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_filemanager_name} not supported" in json["detail"]


def test_get_filemanager_settings(secure_client, secure_client_headers):
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.get(
        f"/file_manager/settings/{file_manager_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == file_manager_name
    assert json["value"] == {}
    assert json["scheme"]["fileManagerName"] == file_manager_name
    assert json["scheme"]["type"] == "object"
