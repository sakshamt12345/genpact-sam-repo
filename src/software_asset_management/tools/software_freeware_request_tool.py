import os
import json
from typing import Type, Any

import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


class SoftwareRequestInput(BaseModel):
    """Input schema for creating a ServiceNow software request."""

    ohr: str = Field(
        ...,
        description="The 9-digit employee OHR number."
    )

    serial_number: str = Field(
        ...,
        description="The service tag or serial number of the machine "
                    "where software installation is required."
    )

    software_name: str = Field(
        ...,
        description="Name of the software requested for installation."
    )

    version: str = Field(
        ...,
        description="Version of the software requested."
    )


class SoftwareRequest(BaseTool):
    name: str = "create_software_request"
    description: str = (
        "Verifies a Genpact user in ServiceNow using their OHR, retrieves "
        "their user details, creates a ServiceNow software request for the "
        "specified machine and software, and retrieves the resulting "
        "Requested Item (RITM) details."
    )
    args_schema: Type[BaseModel] = SoftwareRequestInput

    def _run(
        self,
        ohr: str,
        serial_number: str,
        software_name: str,
        version: str,
    ) -> str:

        try:

            instance_url = os.getenv(
                "SERVICENOW_INSTANCE_URL",
                "https://genpactdevelop.service-now.com"
            )

            token_url = os.getenv(
                "SERVICENOW_TOKEN_URL",
                f"{instance_url}/oauth_token.do"
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

            string_ohr = str(ohr).strip()
            string_serial_number = str(serial_number).strip()
            string_software_name = str(software_name).strip()
            string_version = str(version).strip()

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

            # Optional OHR validation
            if not string_ohr.isdigit() or len(string_ohr) != 9:
                return self._json_response({
                    "status": "error",
                    "message": "OHR must be a 9-digit employee code."
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

            try:
                token_data = token_response.json()
            except ValueError:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "ServiceNow token endpoint did not "
                        "return valid JSON."
                    )
                })

            if not token_response.ok:
                return self._json_response({
                    "status": "error",
                    "message": (
                        token_data.get("error_description")
                        or token_data.get("error")
                        or "ServiceNow authentication failed."
                    )
                })

            access_token = token_data.get("access_token")

            if not access_token:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "Authentication failed: "
                        "Unable to retrieve access token."
                    )
                })


            user_url = (
                f"{instance_url}/api/now/table/sys_user"
            )

            user_headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            user_params = {
                "sysparm_query": f"user_name={string_ohr}",
                "sysparm_display_value": "true",
            }

            user_response = requests.get(
                user_url,
                headers=user_headers,
                params=user_params,
                timeout=30,
            )

            try:
                user_body = user_response.json()
            except ValueError:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "ServiceNow user API did not "
                        "return valid JSON."
                    )
                })

            if not user_response.ok:
                return self._json_response({
                    "status": "error",
                    "message": (
                        user_body.get("error", {}).get("message")
                        if isinstance(user_body.get("error"), dict)
                        else user_body.get("message")
                        or "Failed to retrieve user details."
                    )
                })

            results = user_body.get("result", [])

            if not results:
                return self._json_response({
                    "status": "error",
                    "message": (
                        f"User not found for OHR {string_ohr}"
                    )
                })

            raw_user = results[0]


            manager = raw_user.get("manager")

            if isinstance(manager, dict):
                manager_name = manager.get("display_value", "")
            else:
                manager_name = ""

            ticket_user_data = {
                "user_email": raw_user.get("email", ""),
                "var_requested_for": raw_user.get("sys_id", ""),
                "requested_for": "true",
                "ohr_id": raw_user.get(
                    "user_name",
                    string_ohr
                ),
                "fullname": raw_user.get("name", ""),
                "managername": manager_name,
            }


            ticket_url = (
                f"{instance_url}/api/sn_sc/servicecatalog/"
                "items/180a12c487c603106c60a9383cbb3576/order_now"
            )

            ticket_payload = {
                "sysparm_quantity": "1",

                "variables": {
                    "user_email": ticket_user_data["user_email"],

                    "userband": "",

                    "var_requested_for":
                        ticket_user_data["var_requested_for"],

                    "requested_for":
                        ticket_user_data["requested_for"],

                    "ohr_id":
                        ticket_user_data["ohr_id"],

                    "fullname":
                        ticket_user_data["fullname"],

                    "managername":
                        ticket_user_data["managername"],

                    (
                        "is_the_required_software_is_available_"
                        "in_the_self_service_client"
                    ): "No",

                    "asset_type": "Desktop or Laptop",

                    "single_or_multi_user": "Single User",

                    (
                        "please_enter_service_tag_serial_number_"
                        "of_machine_where_installation_is_needed"
                    ): string_serial_number,

                    "select_software": string_software_name,

                    "software_version": string_version,

                    "agreement": "true",
                },

                "sysparm_no_validation": "true",

                "referrer": None,
            }

            ticket_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            ticket_response = requests.post(
                ticket_url,
                headers=ticket_headers,
                json=ticket_payload,
                timeout=30,
            )

            try:
                ticket_result = ticket_response.json()
            except ValueError:
                ticket_result = ticket_response.text

            if not ticket_response.ok:
                if isinstance(ticket_result, dict):
                    error_message = (
                        ticket_result.get("message")
                        or ticket_result.get("error")
                        or json.dumps(ticket_result, default=str)
                    )
                else:
                    error_message = str(ticket_result)

                return self._json_response({
                    "status": "error",
                    "message": (
                        f"Failed to create ServiceNow request: "
                        f"{error_message}"
                    ),
                    "http_status": ticket_response.status_code,
                })


            if isinstance(ticket_result, dict):
                request_number = (
                    ticket_result.get("request_number")
                    or ticket_result.get("result", {}).get(
                        "request_number"
                    )
                    if isinstance(
                        ticket_result.get("result", {}),
                        dict
                    )
                    else ticket_result.get("request_number")
                )
            else:
                request_number = None


            requested_item_result = {}

            if request_number:

                requested_item_url = (
                    f"{instance_url}/api/now/table/sc_req_item"
                )

                requested_item_params = {
                    "sysparm_query":
                        f"request.number={request_number}",
                    "sysparm_fields":
                        "number,sys_id",
                    "sysparm_limit": "1",
                }

                requested_item_response = requests.get(
                    requested_item_url,
                    headers=user_headers,
                    params=requested_item_params,
                    timeout=30,
                )

                try:
                    requested_item_body = (
                        requested_item_response.json()
                    )
                except ValueError:
                    requested_item_body = {}

                if requested_item_response.ok:
                    ritm_results = requested_item_body.get(
                        "result",
                        []
                    )

                    if ritm_results:
                        requested_item_result = ritm_results[0]


            return self._json_response({
                "status": "success",
                "User_detail": ticket_user_data,
                "Ticket_Request": ticket_result,
                "Request_Number": request_number,
                "Requested_Item": requested_item_result,
            })

        except requests.exceptions.Timeout:
            return self._json_response({
                "status": "error",
                "message": (
                    "Request timed out while communicating "
                    "with ServiceNow."
                ),
            })

        except requests.exceptions.ConnectionError as error:
            return self._json_response({
                "status": "error",
                "message": (
                    f"Unable to connect to ServiceNow: {str(error)}"
                ),
            })

        except requests.exceptions.RequestException as error:
            return self._json_response({
                "status": "error",
                "message": (
                    f"ServiceNow request failed: {str(error)}"
                ),
            })

        except Exception as error:
            return self._json_response({
                "status": "error",
                "message": str(error),
            })

    @staticmethod
    def _json_response(data: dict[str, Any]) -> str:
        return json.dumps(data, default=str)
