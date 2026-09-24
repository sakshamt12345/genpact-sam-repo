import os
from typing import Type, Any

import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


class AuthenticationInput(BaseModel):
    """Input schema for user authentication."""

    ohr: str = Field(
        ...,
        description="The 9-digit employee OHR number used to authenticate the user."
    )


class Authentication(BaseTool):
    name: str = "authenticate_user"
    description: str = (
        "Authenticates a Genpact user against ServiceNow using their 9-digit OHR, "
        "retrieves their user profile, removes sensitive/unnecessary fields, and "
        "returns the verified user details."
    )
    args_schema: Type[BaseModel] = AuthenticationInput

    def _run(self, ohr: str) -> str:
        try:
            token_url = os.getenv(
                "SERVICENOW_TOKEN_URL",
                "https://genpactuat.service-now.com/oauth_token.do"
            )

            client_id = os.getenv("SERVICENOW_CLIENT_ID_UAT")
            client_secret = os.getenv("SERVICENOW_CLIENT_SECRET_UAT")
            username = os.getenv("SERVICENOW_USERNAME_UAT")
            password = os.getenv("SERVICENOW_PASSWORD_UAT")

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
                        "Unable to retrieve ServiceNow access token."
                    )
                })

            string_ohr = str(ohr).strip()

            if not string_ohr.isdigit() or len(string_ohr) != 9:
                return self._json_response({
                    "status": "error",
                    "message": "OHR must be a 9-digit employee code."
                })


            user_url = (
                "https://genpactuat.service-now.com/api/now/table/sys_user"
            )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            params = {
                "sysparm_query": f"user_name={string_ohr}",
                "sysparm_display_value": "true",
            }

            user_response = requests.get(
                user_url,
                headers=headers,
                params=params,
                timeout=30,
            )

            user_response.raise_for_status()
            user_body = user_response.json()

            results = user_body.get("result", [])

            if not results:
                return self._json_response({
                    "status": "error",
                    "message": f"User not found for OHR: {string_ohr}"
                })

            raw_user = results[0]

            field_blacklist = {
                "sys_domain_path",
                "sys_mod_count",
                "internal_id_links",
                "processId",
                "failed_attempts",
                "u_nature_of_work",
                "u_account_name",
                "u_service_line",
                "sys_created_by",
                "identity_type",
                "u_coe",
                "notification",
                "federated_id",
                "company",
                "sys_domain",
                "u_employee_status",
                "expires_in",
                "token_type",
                "last_login_time",
                "sys_created_on",
                "calendar_integration",
                "sys_updated_by",
                "sys_updated_on",
                "last_login",
                "u_parent_location",
                "name",
            }

            cleaned_user = {}

            for key, value in raw_user.items():

                if key in field_blacklist:
                    continue

                if value is None:
                    continue

                if isinstance(value, dict):
                    nested_obj = {}

                    for nested_key, nested_value in value.items():

                        # Remove ServiceNow links
                        if nested_key == "link":
                            continue

                        if nested_value in ("", None):
                            continue

                        nested_obj[nested_key] = nested_value

                    if nested_obj:
                        cleaned_user[key] = nested_obj

                    continue

                if isinstance(value, str):
                    trimmed_value = value.strip()

                    if not trimmed_value:
                        continue

                    if trimmed_value.lower() == "false":
                        continue

                    cleaned_user[key] = trimmed_value
                    continue

                # 5. Numbers / booleans / other values
                cleaned_user[key] = value

            return self._json_response({
                "status": "success",
                "verified": True,
                "User_detail": cleaned_user,
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
        import json
        return json.dumps(data, default=str)
