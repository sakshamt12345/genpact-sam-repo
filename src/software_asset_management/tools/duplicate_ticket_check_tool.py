import os
import json
from typing import Type, Any

import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


class DuplicateTicketCheckInput(BaseModel):
    """Input schema for duplicate ticket checking."""

    ohr: str = Field(
        ...,
        description="The employee OHR number for whom the request is being raised."
    )

    nl_context: str = Field(
        ...,
        description="The natural-language context describing the software-related request."
    )

    on_behalf: str = Field(
        default="NA",
        description=(
            "OHR of the employee on whose behalf the request is being raised. "
            "Use 'NA' when the request is for the original OHR."
        )
    )


class DuplicateTicketCheck(BaseTool):
    name: str = "check_duplicate_software_ticket"

    description: str = (
        "Checks whether a matching ServiceNow catalog ticket already exists "
        "for an employee's software-related request. Uses the on-behalf OHR "
        "when provided, otherwise uses the original OHR. Returns the ticket "
        "creation flag and any matching tickets found."
    )

    args_schema: Type[BaseModel] = DuplicateTicketCheckInput

    def _run(
        self,
        ohr: str,
        nl_context: str,
        on_behalf: str = "NA",
    ) -> str:

        try:
            OHR = str(ohr or "").strip()
            nl_context = str(nl_context or "").strip()

            if on_behalf != "NA":
                on_behalf = str(on_behalf or "").strip()
            else:
                on_behalf = ""

            effective_ohr = on_behalf or OHR

            catalog_sysid = "180a12c487c603106c60a9383cbb3576"

            matching_ticket = []

            nl_context = nl_context + "(Software Related Request)"

            print("OHR:", OHR)
            print("On Behalf:", on_behalf)
            print("Effective OHR:", effective_ohr)
            print("NL Context:", nl_context)


            duplicate_check_url = os.getenv(
                "DUPLICATE_TICKET_CHECK_URL",
                "https://websocket-kore-g4e0dyftcvdgcjau."
                "swedencentral-01.azurewebsites.net/find_catalog"
            )

            api_key = os.getenv("TICKET_CREATION_API_KEY")

            if not api_key:
                return self._json_response({
                    "status": "error",
                    "message": (
                        "Missing configuration: "
                        "DUPLICATE_TICKET_API_KEY"
                    )
                })

            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }

            payload = {
                "ohr": effective_ohr,
                "catalog_sysid": catalog_sysid,
            }

            response = requests.post(
                duplicate_check_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            print("Response Status:", response.status_code)

            response.raise_for_status()

            data = response.json()

            print(
                "API Response:",
                json.dumps(data, indent=2, default=str)
            )


            if data and isinstance(data.get("matching_ticket"), list):
                matching_ticket = data["matching_ticket"]

            print(
                "matching_ticket:",
                json.dumps(matching_ticket, indent=2, default=str)
            )

            print(
                "matching_ticket length:",
                len(matching_ticket)
            )

            flag = (
                "@@TICKET_CREATE@@"
                + OHR
                + "@@"
                + catalog_sysid
                + "@@"
                + nl_context
                + "@@"
                + effective_ohr
                + "@@"
            )

            print("Generated Flag:", flag)


            if len(matching_ticket) > 0:

                print(
                    "Returning object with matching tickets."
                )

                return self._json_response({
                    "status": "success",
                    "flag": flag,
                    "matching_ticket": matching_ticket,
                })


            print(
                "No matching tickets found. Returning flag only."
            )

            return flag

        except requests.exceptions.RequestException as error:


            print(
                "Duplicate check failed:",
                str(error)
            )

            catalog_sysid = "180a12c487c603106c60a9383cbb3576"

            flag = (
                "@@TICKET_CREATE@@"
                + OHR
                + "@@"
                + catalog_sysid
                + "@@"
                + nl_context
                + "@@"
                + effective_ohr
                + "@@"
            )

            return flag

        except Exception as error:

            print(
                "Duplicate check failed:",
                str(error)
            )

            catalog_sysid = "180a12c487c603106c60a9383cbb3576"

            flag = (
                "@@TICKET_CREATE@@"
                + OHR
                + "@@"
                + catalog_sysid
                + "@@"
                + nl_context
                + "@@"
                + effective_ohr
                + "@@"
            )

            return flag

    @staticmethod
    def _json_response(data: dict[str, Any]) -> str:
        return json.dumps(data, default=str)
