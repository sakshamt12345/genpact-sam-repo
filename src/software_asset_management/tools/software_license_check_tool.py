import json
import os
from typing import Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SoftwareLicenseCheckInput(BaseModel):
    category: str = Field(
        ...,
        description=(
            "Check category. Must be either "
            "'software_license_check' or 'deny_group_check'."
        ),
    )

    ohr: int = Field(
        ...,
        description="OHR of the employee.",
    )

    software_license_name: str = Field(
        "",
        description=(
            "Software license name. Required when category is "
            "'software_license_check'. Leave blank for 'deny_group_check'."
        ),
    )

    deny_azure_group_name: str = Field(
        "",
        description=(
            "Azure AD group name to check. Required when category is "
            "'deny_group_check'. Leave blank for 'software_license_check'."
        ),
    )


class SoftwareLicenseCheckTool(BaseTool):
    name: str = "Software License Check"

    description: str = (
        "Checks software license or Azure deny-group information for an OHR. "
        "Obtains a Microsoft access token using client credentials and POSTs "
        "the category, OHR, software_license_name, and deny_azure_group_name "
        "to the OPS API. The category determines which value is populated."
    )

    args_schema: Type[BaseModel] = SoftwareLicenseCheckInput

    def _run(
        self,
        category: str,
        ohr: int,
        software_license_name: str = "",
        deny_azure_group_name: str = "",
    ) -> str:

        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        resource = os.getenv(
            "AZURE_RESOURCE",
            f"api://{client_id}" if client_id else "",
        )

        token_url = (
            f"https://login.microsoftonline.com/"
            f"{tenant_id}/oauth2/token"
        )

        ops_api_url = (
            "https://peg-automation.azure-api.net/"
            "db_logging/ops"
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

            category = str(category or "").strip()

            allowed_categories = [
                "software_license_check",
                "deny_group_check",
            ]

            if category not in allowed_categories:
                return json.dumps(
                    {
                        "success": False,
                        "error": (
                            f'Invalid category: "{category}". '
                            'Category must be either '
                            '"software_license_check" or '
                            '"deny_group_check".'
                        ),
                    },
                    indent=2,
                )


            software_license_name = (
                str(software_license_name or "").strip()
            )

            deny_azure_group_name = (
                str(deny_azure_group_name or "").strip()
            )

            if category == "software_license_check":

                if not software_license_name:
                    return json.dumps(
                        {
                            "success": False,
                            "error": (
                                "SOFTWARE_NAME is required when "
                                'category is "software_license_check".'
                            ),
                        },
                        indent=2,
                    )

                # deny_azure_group_name must remain empty
                deny_azure_group_name = ""

            elif category == "deny_group_check":

                if not deny_azure_group_name:
                    return json.dumps(
                        {
                            "success": False,
                            "error": (
                                "DENY_AZURE_GROUP_NAME is required when "
                                'category is "deny_group_check".'
                            ),
                        },
                        indent=2,
                    )

                # software_license_name must remain empty
                software_license_name = ""


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
                    "Content-Type": (
                        "application/x-www-form-urlencoded"
                    ),
                },
                timeout=30,
                verify=False,
            )

            # Read response as text first
            token_text = token_response.text

            try:
                token_data = token_response.json()
            except ValueError:
                raise RuntimeError(
                    "Token endpoint did not return JSON.\n"
                    + token_text
                )

            if (
                not token_response.ok
                or not token_data.get("access_token")
            ):
                raise RuntimeError(
                    token_data.get("error_description")
                    or token_data.get("error")
                    or "Failed to retrieve Microsoft access token."
                )

            access_token = token_data["access_token"]


            request_body = {
                "category": category,
                "OHR": str(ohr),
                "software_license_name": software_license_name,
                "deny_azure_group_name": deny_azure_group_name,
            }

            response = requests.post(
                ops_api_url,
                json=request_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=30,
                verify=False,
            )

            # Read response as text first
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
                    default=str,
                )


            return json.dumps(
                {
                    "success": True,
                    "category": category,
                    "data": response_body,
                },
                indent=2,
                default=str,
            )


        except requests.exceptions.Timeout:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        "Request timed out while calling the "
                        "OPS API."
                    ),
                },
                indent=2,
            )

        except requests.exceptions.RequestException as error:
            return json.dumps(
                {
                    "success": False,
                    "error": (
                        f"HTTP request failed: {str(error)}"
                    ),
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
