from json import dumps
import pytest
from fastapi.encoders import jsonable_encoder

from cat.services.service_factory import ServiceFactory

from tests.utils import api_key


def test_get_all_agentic_workflow_settings(secure_client, secure_client_headers, agent_plugin_manager):
    agentic_workflow_schemas = ServiceFactory(
        agent_plugin_manager,
        factory_allowed_handler_name="factory_allowed_agentic_workflows",
        setting_category="agentic_workflow",
        schema_name="agenticWorkflowName",
    ).get_schemas()
    response = secure_client.get("/agentic_workflow/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(agentic_workflow_schemas)

    for setting in json["settings"]:
        assert setting["name"] in agentic_workflow_schemas.keys()
        assert setting["value"] == {}
        expected_schema = agentic_workflow_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected agentic_workflow
    assert json["selected_configuration"] == "CoreAgenticWorkflowConfig"


def test_get_agentic_workflow_settings_non_existent(secure_client, secure_client_headers):
    non_existent_agentic_workflow_name = "AgenticWorkflowNonExistent"
    response = secure_client.get(
        f"/agentic_workflow/settings/{non_existent_agentic_workflow_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_agentic_workflow_name} not supported" in json["detail"]


@pytest.mark.skip("Have at least another agentic_workflow class to test")
def test_upsert_agentic_workflow_settings(secure_client, secure_client_headers):
    # set a different agentic_workflow from default one (same class different size)
    new_agentic_workflow = "AgenticWorkflowConfig"
    agentic_workflow_config = {"api_key": api_key}
    response = secure_client.put(
        f"/agentic_workflow/settings/{new_agentic_workflow}", json=agentic_workflow_config, headers=secure_client_headers
    )
    json = response.json()

    # verify success
    assert response.status_code == 200
    assert json["name"] == new_agentic_workflow

    # Retrieve all agentic_workflows settings to check if it was saved in DB

    ## We are now forced to use api_key, otherwise we don't get in
    response = secure_client.get("/agentic_workflow/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 403
    assert json["detail"] == "Forbidden"

    ## let's use the configured api_key for http
    response = secure_client.get("/agentic_workflow/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_agentic_workflow

    ## check also specific agentic_workflow endpoint
    response = secure_client.get(f"/agentic_workflow/settings/{new_agentic_workflow}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_agentic_workflow
    assert json["scheme"]["agenticWorkflowName"] == new_agentic_workflow
