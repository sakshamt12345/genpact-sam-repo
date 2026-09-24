import os
import json
from typing import Type, Any

import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


class RITMDetailsInput(BaseModel):
    """Input schema for retrieving software details from a ServiceNow RITM."""

    ritm: str = Field(
        ...,
        description="The ServiceNow RITM number used to retrieve the requested software details."
    )


class RITMDetails(BaseTool):
    name: str = "get_software_details"

    description: str = (
        "Retrieves software name and version details from a ServiceNow RITM. "
        "Authenticates with ServiceNow using OAuth, retrieves the catalog item "
        "options for the RITM, and returns the software name, requested version, "
        "and raw matching results."
    )

    args_schema: Type[BaseModel] = RITMDetailsInput

    def _run(self, ritm: str) -> str:

        try:

            token_url = os.getenv(
                "SERVICENOW_TOKEN_URL",
                "https://genpactdevelop.service-now.com/oauth_token.do"
            )

            client_id = os.getenv("SERVICENOW_CLIENT_ID_DEV")
            client_secret = os.getenv("SERVICENOW_CLIENT_SECRET_DEV")
            username = os.getenv("SERVICENOW_USERNAME_DEV")
            password = os.getenv("SERVICENOW_PASSWORD_DEV")

            required_credentials = {
                "SERVICENOW_CLIENT_ID": client_id,
                "SERVICENOW_CLIENT_SECRET": client_secret,
                "SERVICENOW_USERNAME": username,
                "SERVICENOW_PASSWORD": password,
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
                        "Missing ServiceNow configuration: "
                        + ", ".join(missing)
                    )
                })

            token_payload = {
                "grant_type": "password",
                "client_id": client_id,
                "client_secret": client_secret,
                "username": username,
                "password": password,
            }

            token_response = requests.post(
                token_url,
                data=token_payload,
                timeout=30,
            )

            token_response.raise_for_status()

            token_data = token_response.json()

            access_token = token_data.get("access_token")

            if not access_token:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "Authentication failed: "
                        "Unable to retrieve access token."
                    )
                })


            ritm_number = str(ritm or "").strip()

            if not ritm_number:
                return self._json_response({
                    "status": "error",
                    "message": "RITM number is required."
                })


            option_url = (
                "https://genpactdevelop.service-now.com/"
                "api/now/table/sc_item_option_mtom"
            )

            question_1 = (
                "What is the name of the software you are here for?"
            )

            question_2 = "What version do you need?"

            query = (
                f"request_item.number={ritm_number}"
                "^sc_item_option.item_option_new.question_textIN"
                f"{question_1},{question_2}"
            )

            params = {
                "sysparm_query": query,
                "sysparm_fields": (
                    "sc_item_option.item_option_new.question_text,"
                    "sc_item_option.value"
                ),
            }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            option_response = requests.get(
                option_url,
                headers=headers,
                params=params,
                timeout=30,
            )

            option_response.raise_for_status()

            option_body = option_response.json()


            option_results = option_body.get("result", [])

            software_details = {
                "software_name": "",
                "version": "",
            }

            for item in option_results:

                question = item.get(
                    "sc_item_option.item_option_new.question_text",
                    ""
                )

                value = item.get(
                    "sc_item_option.value",
                    ""
                ) or ""

                if question == question_1:
                    software_details["software_name"] = value

                if question == question_2:
                    software_details["version"] = value

            return self._json_response({
                "status": "success",
                "RITM": ritm_number,
                "Software_Name": software_details["software_name"],
                "Version": software_details["version"],
                "Raw_Result": option_results,
            })

        except requests.exceptions.RequestException as error:

            return self._json_response({
                "status": "error",
                "message": f"ServiceNow request failed: {str(error)}",
            })

        except Exception as error:

            return self._json_response({
                "status": "error",
                "message": str(error),
            })

    @staticmethod
    def _json_response(data: dict[str, Any]) -> str:
        return json.dumps(data, default=str)
