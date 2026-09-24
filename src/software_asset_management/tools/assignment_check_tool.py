import json
import os
from typing import Type, Optional

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class AssignmentCheckInput(BaseModel):
    ohr: str = Field(
        ...,
        description="OHR of the employee (self or on-behalf-of)"
    )
    serial_number: str = Field(
        ...,
        description="Serial number of the selected device"
    )
    software_name: str = Field(
        ...,
        description="Resolved software name to check assignment/install status for"
    )
    version: Optional[str] = Field(
        "",
        description="Always blank for this check"
    )
    source: str = Field(
        "airwatch",
        description="Always 'Airwatch' for this check"
    )


class AssignmentCheckTool(BaseTool):
    name: str = "Software Assignment Check"

    description: str = (
        "Checks whether software is assigned and installed on a device for an OHR. "
        "Obtains a Microsoft access token using client credentials and POSTs "
        "OHR, serial_number, software_name, version, and source to the assignment API. "
        "Returns assignment and installation status, versions, and metadata."
    )

    args_schema: Type[BaseModel] = AssignmentCheckInput

    def _run(
        self,
        ohr: str,
        serial_number: str,
        software_name: str,
        version: str = "",
        source: str = "Airwatch",
    ) -> str:


        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        resource = os.getenv(
            "AZURE_RESOURCE",
            f"api://{client_id}" if client_id else ""
        )

        token_url = (
            f"https://login.microsoftonline.com/"
            f"{tenant_id}/oauth2/token"
        )

        assignment_api_url = (
            "https://peg-automation.azure-api.net/"
            "db_logging/assignment_check"
        )


        missing = []

        if not tenant_id:
            missing.append("AZURE_TENANT_ID")

        if not client_id:
            missing.append("AZURE_CLIENT_ID")

        if not client_secret:
            missing.append("AZURE_CLIENT_SECRET")

        if missing:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        "Missing required environment variables: "
                        + ", ".join(missing)
                    ),
                },
                indent=2,
            )

        try:


            token_payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "resource": resource,
            }

            token_response = requests.post(
                token_url,
                data=token_payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=30,
                verify=False
            )

            print("DEBUG TOKEN STATUS:", token_response.status_code)
            print("DEBUG TOKEN RESPONSE:", token_response.text)

            token_text = token_response.text

            try:
                token_data = token_response.json()
            except ValueError:
                raise RuntimeError(
                    "Token endpoint did not return JSON.\n"
                    + token_text
                )

            if not token_response.ok or not token_data.get("access_token"):
                raise RuntimeError(
                    token_data.get("error_description")
                    or token_data.get("error")
                    or "Failed to retrieve Microsoft access token."
                )

            access_token = token_data["access_token"]


            request_body = {
                "OHR": str(ohr),
                "SERIAL_NUMBER": str(serial_number).strip(),
                "SOFTWARE_NAME": str(software_name).strip(),
                "VERSION": str(version or ""),
                "SOURCE": str(source),
            }
            print(f"DEBUG outgoing payload: {request_body}")


            response = requests.post(
                assignment_api_url,
                json=request_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=30,
            )


            response_text = response.text


            try:
                response_body = response.json()
            except ValueError:
                response_body = response_text


            if not response.ok:
                if isinstance(response_body, dict):
                    error_message = (
                        response_body.get("message")
                        or response_body.get("error")
                        or json.dumps(response_body)
                    )
                else:
                    error_message = response_body

                return json.dumps(
                    {
                        "success": False,
                        "status_code": response.status_code,
                        "error": error_message,
                    },
                    indent=2,
                )


            return json.dumps(
                {
                    "success": True,
                    "data": response_body,
                },
                indent=2,
                default=str,
            )

        except requests.exceptions.Timeout:
            return json.dumps(
                {
                    "success": False,
                    "error": "Request timed out while calling the assignment API.",
                },
                indent=2,
            )

        except requests.exceptions.RequestException as error:
            return json.dumps(
                {
                    "success": False,
                    "error": f"HTTP request failed: {str(error)}",
                },
                indent=2,
            )

        except Exception as error:
            return json.dumps(
                {
                    "success": False,
                    "error": str(error),
                },
                indent=2,
            )
