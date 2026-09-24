import os
import json
from typing import Type, Any

import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


class SoftwareInstallationInput(BaseModel):
    """Input schema for software installation/removal logging."""

    ohr: str = Field(
        ...,
        description="The 9-digit employee OHR number."
    )

    serial_number: str = Field(
        ...,
        description="The serial number of the device."
    )

    software_name: str = Field(
        ...,
        description="Name of the software being installed or removed."
    )

    version: str = Field(
        ...,
        description="Version of the software."
    )

    source: str = Field(
        ...,
        description="Source of the software installation/removal request."
    )


class SoftwareInstallation(BaseTool):
    name: str = "software_installation"
    description: str = (
        "Logs a software installation or removal request by authenticating "
        "with Microsoft Azure AD using client credentials and then calling "
        "the Pegasus automation installation/removal API."
    )
    args_schema: Type[BaseModel] = SoftwareInstallationInput

    def _run(
        self,
        ohr: str,
        serial_number: str,
        software_name: str,
        version: str,
        source: str,
    ) -> str:
        try:
            tenant_id = os.getenv("AZURE_TENANT_ID")
            client_id = os.getenv("AZURE_CLIENT_ID")
            client_secret = os.getenv("AZURE_CLIENT_SECRET")

            resource = os.getenv(
                "AZURE_RESOURCE",
                f"api://{client_id}" if client_id else None
            )

            token_url = os.getenv(
                "AZURE_TOKEN_URL",
                f"https://login.microsoftonline.com/"
                f"{tenant_id}/oauth2/token"
                if tenant_id
                else None
            )

            required_credentials = {
                "AZURE_TENANT_ID": tenant_id,
                "AZURE_CLIENT_ID": client_id,
                "AZURE_CLIENT_SECRET": client_secret,
                "AZURE_RESOURCE": resource,
            }

            missing = [
                key
                for key, value in required_credentials.items()
                if not value
            ]

            if missing:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "Missing Microsoft Azure configuration: "
                        + ", ".join(missing)
                    )
                })

            string_ohr = str(ohr).strip()
            string_serial_number = str(serial_number).strip()
            string_software_name = str(software_name).strip()
            string_version = str(version).strip()
            string_source = str(source).strip()

            if not string_ohr:
                return self._json_response({
                    "status": "error",
                    "message": "OHR is required."
                })

            if not string_serial_number:
                return self._json_response({
                    "status": "error",
                    "message": "Serial number is required."
                })

            if not string_software_name:
                return self._json_response({
                    "status": "error",
                    "message": "Software name is required."
                })

            if not string_version:
                return self._json_response({
                    "status": "error",
                    "message": "Software version is required."
                })

            if not string_source:
                return self._json_response({
                    "status": "error",
                    "message": "Source is required."
                })


            token_payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "resource": resource,
            }

            token_response = requests.post(
                token_url,
                data=token_payload,
                timeout=30,
                verify=False
            )

            try:
                token_data = token_response.json()
            except ValueError:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "Token endpoint did not return valid JSON."
                    )
                })

            if not token_response.ok:
                return self._json_response({
                    "status": "error",
                    "message": (
                        token_data.get("error_description")
                        or token_data.get("error")
                        or "Failed to retrieve Microsoft access token."
                    )
                })

            access_token = token_data.get("access_token")

            if not access_token:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "Authentication failed: "
                        "Unable to retrieve Microsoft access token."
                    )
                })


            api_url = os.getenv(
                "SOFTWARE_INSTALLATION_API_URL",
                "https://peg-automation.azure-api.net/"
                "db_logging/scout-installation-removal"
            )

            request_body = {
                "OHR": string_ohr,
                "SERIAL_NUMBER": string_serial_number,
                "SOFTWARE_NAME": string_software_name,
                "VERSION": string_version,
                "SOURCE": string_source,
            }

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }

            response = requests.post(
                api_url,
                headers=headers,
                json=request_body,
                timeout=30,
                verify=False
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
                        or json.dumps(response_body, default=str)
                    )
                else:
                    error_message = response_body

                return self._json_response({
                    "status": "error",
                    "http_status": response.status_code,
                    "message": str(error_message),
                })


            return self._json_response({
                "status": "success",
                "message": "Installation request completed successfully.",
                "data": response_body,
            })

        except requests.exceptions.Timeout:
            return self._json_response({
                "status": "error",
                "message": "Request timed out while communicating with the API.",
            })

        except requests.exceptions.ConnectionError as error:
            return self._json_response({
                "status": "error",
                "message": (
                    f"Unable to connect to the requested API: {str(error)}"
                ),
            })

        except requests.exceptions.RequestException as error:
            return self._json_response({
                "status": "error",
                "message": f"API request failed: {str(error)}",
            })

        except Exception as error:
            return self._json_response({
                "status": "error",
                "message": str(error),
            })

    @staticmethod
    def _json_response(data: dict[str, Any]) -> str:
        return json.dumps(data, default=str)
