import os
from typing import Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SoftwareLibraryInput(BaseModel):
    query: str = Field(
        default="",
        description=(
            "Optional software name or keyword. The tool returns the full approved "
            "software catalog so the LLM can match the user's informal software name "
            "against the exact catalog name."
        ),
    )


class SoftwareLibraryTool(BaseTool):
    name: str = "Software Library Lookup"

    description: str = (
        "Returns the full list of software names available in the organization's "
        "ServiceNow software catalog. Use this to match a user's informal or "
        "abbreviated software name against the exact catalog name before proceeding "
        "with an install, uninstall, or renewal request."
    )

    args_schema: Type[BaseModel] = SoftwareLibraryInput

    def _run(self, query: str = "") -> str:
        try:
            token_url = (
                "https://genpactdevelop.service-now.com/oauth_token.do"
            )

            client_id = os.getenv("SERVICENOW_CLIENT_ID_DEV")
            client_secret = os.getenv("SERVICENOW_CLIENT_SECRET_DEV")
            username = os.getenv("SERVICENOW_USERNAME_DEV")
            password = os.getenv("SERVICENOW_PASSWORD_DEV")

            if not all(
                [client_id, client_secret, username, password]
            ):
                raise ValueError(
                    "ServiceNow OAuth credentials are not configured."
                )

            token_response = requests.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "username": username,
                    "password": password,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=30,
            )

            token_response.raise_for_status()

            token_data = token_response.json()

            access_token = token_data.get("access_token")

            if not access_token:
                raise RuntimeError(
                    "Unable to fetch ServiceNow OAuth token."
                )

            software_url = (
                "https://genpactdevelop.service-now.com/api/now/table/"
                "x_ggisu_software_0_software_data_table"
            )

            software_response = requests.get(
                software_url,
                params={
                    "sysparm_fields": "software_name",
                    "active": "true",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
            )

            software_response.raise_for_status()

            software_data = software_response.json()

            software_names = [
                item.get("software_name")
                for item in software_data.get("result", [])
                if item.get("software_name")
            ]

            if not software_names:
                return "No software names found in the ServiceNow catalog."

            return "\n".join(software_names)

        except requests.RequestException as error:
            return f"ServiceNow API error: {str(error)}"

        except Exception as error:
            return f"Software Library Lookup error: {str(error)}"