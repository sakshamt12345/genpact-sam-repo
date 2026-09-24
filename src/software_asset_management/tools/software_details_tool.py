import os
from typing import Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SoftwareDetailsInput(BaseModel):
    software_name: str = Field(
        ...,
        description=(
            "Exact software name to search for in the ServiceNow software catalog."
        ),
    )


class SoftwareDetailsTool(BaseTool):
    name: str = "Software Details Lookup"

    description: str = (
        "Looks up an active software record in the organization's ServiceNow "
        "software catalog using the exact software name. Returns software name, "
        "version, tooltip text, cost, blacklist status, trial availability, "
        "category, and active status."
    )

    args_schema: Type[BaseModel] = SoftwareDetailsInput

    def _run(self, software_name: str) -> dict:
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
                    "Authentication failed: Unable to retrieve access token."
                )

            software_name = str(software_name).strip()

            if not software_name:
                raise ValueError("Software name cannot be empty.")

            software_url = (
                "https://genpactdevelop.service-now.com/api/now/table/"
                "x_ggisu_software_0_software_data_table"
            )

            software_response = requests.get(
                software_url,
                params={
                    "sysparm_query": (
                        f"software_name={software_name}^active=true"
                    ),
                    "sysparm_fields": (
                        "software_name,"
                        "version,"
                        "tooltip_text,"
                        "cost,"
                        "blacklisted,"
                        "category,"
                        "status,"
                        "active,"
                        "available_for_trial,"
                    ),
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
                timeout=30,
            )

            software_response.raise_for_status()

            software_body = software_response.json()

            software_records = [
                {
                    "software_name": record.get("software_name"),
                    "version": record.get("version"),
                    "tooltip_text": record.get("tooltip_text"),
                    "cost": record.get("cost"),
                    "blacklisted": record.get("blacklisted"),
                    "active": record.get("active"),
                    "category": record.get("category"),
                    "available_for_trial": record.get("available_for_trial"),
                }
                for record in software_body.get("result", [])
            ]

            return {
                "softwareRecords": software_records
            }

        except requests.RequestException as error:
            return {
                "status": "error",
                "message": f"ServiceNow API error: {str(error)}",
            }

        except Exception as error:
            return {
                "status": "error",
                "message": str(error),
            }
