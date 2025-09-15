from enum import Enum
from typing import Any, List
from pydantic import BaseModel, Field

from cat.experimental.mcp_client import CatMcpClient, CatMcpDiscoveredProcedure, mcp_client


@mcp_client
class MockMcpClient(CatMcpClient):
    name = "mock_mcp_client"
    description = "Mock MCP Client for testing"
    host = "localhost"
    port = 50051
    use_tls = False
    service_name = "MockService"

    class MockRequest(BaseModel):
        param1: str
        param2: int
        param3: bool = Field(default=True)
        param4: Enum = Field(default="option1", description="An example enum parameter")
        param5: float = Field(default=0.0, ge=0.0, le=100.0)
        param6: list[str] = Field(default_factory=list)

    class MockResponse(BaseModel):
        result: str
        code: int
        details: dict = Field(default_factory=dict)

        def __str__(self):
            return f"MockResponse(result={self.result}, code={self.code}, details={self.details})"

    def discover_procedures(self) -> List[CatMcpDiscoveredProcedure]:
        return [
            CatMcpDiscoveredProcedure(
                name="mock_procedure",
                description="A mock procedure for testing",
                request_model=self.MockRequest,
                response_model=self.MockResponse,
                examples=[
                    "Call mock_procedure with param1='test', param2=42",
                    "Execute mock_procedure with param1='example', param2=10, param3=False"
                ]
            )
        ]

    def _execute_remote_procedure(self, procedure_name: str, **kwargs: Any) -> Any:
        if procedure_name != "mock_procedure":
            raise ValueError(f"Procedure {procedure_name} not found")

        # Simulate processing the request and returning a response
        request = self.MockRequest(**kwargs)
        response = self.MockResponse(
            result=f"Processed {request.param1} with param2={request.param2}",
            code=200,
            details={"param3": request.param3, "param4": request.param4, "param5": request.param5, "param6": request.param6}
        )
        return response
